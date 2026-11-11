"""Cliente de Florida Oberta (Moodle) mediante Playwright, sin token de API.

Inicia sesión rellenando el formulario de login como haría una persona, guarda
el estado de la sesión (cookies) en data/storage_state.json y lo reutiliza en
las siguientes operaciones. Si la sesión ha caducado, vuelve a iniciar sesión.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from ..config import Settings
from . import selectors as S

log = logging.getLogger(__name__)


class MoodleError(Exception):
    """Error genérico de la integración con Moodle."""


class MoodleLoginError(MoodleError):
    """Credenciales incorrectas o login no reconocido."""


@dataclass
class Credentials:
    username: str
    password: str


class MoodleClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.moodle_base_url:
            raise MoodleError("Falta MOODLE_BASE_URL en backend/.env")
        self.settings = settings
        self.base = settings.moodle_base_url
        # Una sola operación de navegador a la vez: evita sesiones cruzadas.
        self._lock = asyncio.Lock()

    def url(self, path: str) -> str:
        return self.base + path

    # ------------------------------------------------------------------ infra
    @asynccontextmanager
    async def _context(self) -> AsyncIterator[BrowserContext]:
        async with async_playwright() as pw:
            launch_kwargs: dict = {"headless": self.settings.headless}
            if self.settings.chromium_executable:
                launch_kwargs["executable_path"] = self.settings.chromium_executable
            browser: Browser = await pw.chromium.launch(**launch_kwargs)
            try:
                state = self.settings.storage_state_path
                context = await browser.new_context(
                    storage_state=str(state) if state.exists() else None,
                    locale="es-ES",
                )
                context.set_default_timeout(self.settings.timeout_ms)
                yield context
            finally:
                await browser.close()

    async def _save_state(self, context: BrowserContext) -> None:
        path = self.settings.storage_state_path
        await context.storage_state(path=str(path))
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def clear_session(self) -> None:
        self.settings.storage_state_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------ login
    async def _is_logged_in(self, page: Page) -> bool:
        if S.LOGIN_PATH in page.url:
            return False
        if await page.locator(S.LOGGED_IN_MARKER).count() > 0:
            return True
        sesskey = await page.evaluate(S.JS_SESSKEY)
        # Moodle asigna sesskey también a invitados; exigimos no estar en login.
        return bool(sesskey) and await page.locator(S.LOGIN_PASSWORD).count() == 0

    async def _login(self, page: Page, creds: Credentials) -> None:
        await page.goto(self.url(S.LOGIN_PATH), wait_until="domcontentloaded")
        if await self._is_logged_in(page):
            return
        try:
            await page.locator(S.LOGIN_USERNAME).first.fill(creds.username)
            await page.locator(S.LOGIN_PASSWORD).first.fill(creds.password)
        except PlaywrightTimeout as exc:
            raise MoodleLoginError(
                "No se encontró el formulario de login. Revisa MOODLE_BASE_URL o "
                "los selectores LOGIN_* en app/moodle/selectors.py"
            ) from exc
        async with page.expect_navigation(wait_until="domcontentloaded"):
            await page.locator(S.LOGIN_SUBMIT).first.click()

        if await self._is_logged_in(page):
            return
        error = page.locator(S.LOGIN_ERROR)
        if await error.count() > 0:
            msg = (await error.first.inner_text()).strip()
            raise MoodleLoginError(msg or "Usuario o contraseña incorrectos")
        raise MoodleLoginError("El login no se completó (¿SSO, captcha o cambio de página?)")

    @asynccontextmanager
    async def session(self, creds: Credentials) -> AsyncIterator[Page]:
        """Página con sesión iniciada (reutilizando cookies si siguen válidas)."""
        async with self._lock:
            async with self._context() as context:
                page = await context.new_page()
                try:
                    await page.goto(self.url(S.DASHBOARD_PATH), wait_until="domcontentloaded")
                    if not await self._is_logged_in(page):
                        log.info("Sesión no válida o caducada: iniciando sesión en Moodle")
                        await self._login(page, creds)
                    await self._save_state(context)
                    yield page
                    await self._save_state(context)
                except PlaywrightTimeout as exc:
                    raise MoodleError(f"Moodle tardó demasiado en responder: {exc.message}") from exc
                except PlaywrightError as exc:
                    raise MoodleError(f"Error de navegador: {exc.message}") from exc

    async def check_login(self, creds: Credentials) -> dict:
        """Inicia sesión (forzando login real) y devuelve info básica del usuario."""
        self.clear_session()
        async with self.session(creds) as page:
            name = None
            el = page.locator(S.USER_FULLNAME)
            if await el.count() > 0:
                name = (await el.first.inner_text()).strip() or None
            return {"ok": True, "user": name}

    # ---------------------------------------------------------------- cursos
    async def list_courses(self, creds: Credentials) -> list[dict]:
        async with self.session(creds) as page:
            courses = await self._courses_via_ajax(page)
            if courses is None:
                log.warning("AJAX de cursos no disponible; usando lectura del DOM")
                courses = await self._courses_via_dom(page)
            return courses

    async def _courses_via_ajax(self, page: Page) -> list[dict] | None:
        sesskey = await page.evaluate(S.JS_SESSKEY)
        if not sesskey:
            return None
        payload = [{
            "index": 0,
            "methodname": S.AJAX_COURSES_METHOD,
            "args": {"offset": 0, "limit": 0, "classification": "all", "sort": "fullname"},
        }]
        resp = await page.request.post(
            self.url(f"{S.AJAX_SERVICE_PATH}?sesskey={sesskey}&info={S.AJAX_COURSES_METHOD}"),
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        if not resp.ok:
            return None
        try:
            body = await resp.json()
            first = body[0]
        except (ValueError, KeyError, IndexError, TypeError):
            return None
        if first.get("error"):
            log.warning("Moodle AJAX devolvió error: %s", first.get("exception"))
            return None
        out = []
        for c in first.get("data", {}).get("courses", []):
            out.append({
                "id": int(c["id"]),
                "fullname": c.get("fullname") or c.get("shortname") or f"Curso {c['id']}",
                "shortname": c.get("shortname"),
                "category": c.get("coursecategory"),
                "url": c.get("viewurl") or self.url(S.COURSE_VIEW_PATH.format(id=c["id"])),
            })
        return out

    async def _courses_via_dom(self, page: Page) -> list[dict]:
        await page.goto(self.url(S.MY_COURSES_PATH), wait_until="domcontentloaded")
        try:
            await page.locator(S.COURSE_LIST_READY).first.wait_for(timeout=self.settings.timeout_ms)
        except PlaywrightTimeout:
            pass  # seguimos con lo que haya
        seen: dict[int, dict] = {}
        links = page.locator(S.COURSE_LINK)
        for i in range(await links.count()):
            link = links.nth(i)
            href = await link.get_attribute("href") or ""
            ids = parse_qs(urlparse(href).query).get("id")
            if not ids or not ids[0].isdigit():
                continue
            cid = int(ids[0])
            named = link.locator(S.COURSE_NAME)
            name = (await (named.first if await named.count() else link).inner_text()).strip()
            if cid in seen and not name:
                continue
            if cid not in seen or (name and len(name) > len(seen[cid]["fullname"])):
                seen[cid] = {
                    "id": cid,
                    "fullname": " ".join(name.split()) or f"Curso {cid}",
                    "shortname": None,
                    "category": None,
                    "url": href,
                }
        return sorted(seen.values(), key=lambda c: c["fullname"].lower())
