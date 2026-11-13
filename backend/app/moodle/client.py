"""Cliente de Florida Oberta (Moodle) mediante Playwright, sin token de API.

Florida Oberta inicia sesión con la cuenta de Microsoft (Office 365). El cliente
recorre ese flujo como lo haría una persona: botón de Microsoft en Moodle,
correo, contraseña, verificación en dos pasos (MFA) y "¿Mantener la sesión?".

La MFA NUNCA se salta ni se automatiza: la app muestra en la tablet el número o
pide el código, y eres tú quien aprueba en Microsoft Authenticator.

Las cookies resultantes se guardan cifradas (SessionStore) y se reutilizan; si
la sesión caduca y Microsoft vuelve a pedir MFA, la API responde 409 y la
tablet te pide reconectar.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Protocol
from urllib.parse import parse_qs, urlparse

from playwright.async_api import BrowserContext, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from ..config import Settings
from ..session_store import SessionStore
from . import selectors as S

log = logging.getLogger(__name__)


class MoodleError(Exception):
    """Error genérico de la integración con Moodle."""


class MoodleLoginError(MoodleError):
    """Credenciales rechazadas o flujo de login no reconocido."""


class MoodleAuthRequired(MoodleError):
    """Hace falta un login interactivo (sesión caducada, MFA o falta la contraseña)."""


class MoodleBusy(MoodleError):
    """Hay un inicio de sesión interactivo en curso."""


@dataclass
class Credentials:
    username: str
    password: str | None  # None si el usuario eligió no recordarla


class LoginUI(Protocol):
    """Canal con la tablet durante el login interactivo."""

    async def update(self, state: str, **info: object) -> None: ...

    async def request_code(self) -> str: ...


class SilentUI:
    """Login en segundo plano: si Microsoft pide intervención humana, se aborta."""

    async def update(self, state: str, **info: object) -> None:
        if state.startswith("mfa"):
            raise MoodleAuthRequired(
                "Microsoft pide verificación en dos pasos: vuelve a conectar desde la app"
            )

    async def request_code(self) -> str:
        raise MoodleAuthRequired("Microsoft pide un código de verificación: vuelve a conectar desde la app")


def visible(selector: str) -> str:
    """Añade :visible a cada alternativa de un selector con comas."""
    return ", ".join(f"{part.strip()}:visible" for part in selector.split(","))


class MoodleClient:
    def __init__(self, settings: Settings, store: SessionStore) -> None:
        if not settings.moodle_base_url:
            raise MoodleError("Falta MOODLE_BASE_URL en backend/.env")
        self.settings = settings
        self.store = store
        self.base = settings.moodle_base_url
        self._lock = asyncio.Lock()  # una operación de navegador a la vez
        self._interactive = False

    def url(self, path: str) -> str:
        return self.base + path

    # ------------------------------------------------------------------ infra
    @asynccontextmanager
    async def _context(self, headless: bool | None = None, fresh: bool = False) -> AsyncIterator[BrowserContext]:
        async with async_playwright() as pw:
            launch_kwargs: dict = {"headless": self.settings.headless if headless is None else headless}
            if self.settings.chromium_executable:
                launch_kwargs["executable_path"] = self.settings.chromium_executable
            browser = await pw.chromium.launch(**launch_kwargs)
            try:
                context = await browser.new_context(
                    storage_state=None if fresh else self.store.load(),
                    locale="es-ES",
                )
                context.set_default_timeout(self.settings.timeout_ms)
                yield context
            finally:
                await browser.close()

    async def _save_state(self, context: BrowserContext) -> None:
        self.store.save(await context.storage_state())

    async def _visible(self, page: Page, selector: str) -> bool:
        try:
            return await page.locator(visible(selector)).count() > 0
        except PlaywrightError:  # la página está navegando
            return False

    async def _click(self, page: Page, selector: str) -> None:
        await page.locator(visible(selector)).first.click()

    async def _text(self, page: Page, selector: str) -> str:
        try:
            return " ".join((await page.locator(visible(selector)).first.inner_text()).split())
        except PlaywrightError:
            return ""

    # -------------------------------------------------------- estado de login
    def _on_moodle(self, page: Page) -> bool:
        return page.url.startswith(self.base)

    async def _is_logged_in(self, page: Page) -> bool:
        if not self._on_moodle(page) or S.LOGIN_PATH in page.url:
            return False
        try:
            if await page.locator(S.LOGGED_IN_MARKER).count() > 0:
                return True
            sesskey = await page.evaluate(S.JS_SESSKEY)
            return bool(sesskey) and await page.locator(S.LOGIN_PASSWORD).count() == 0
        except PlaywrightError:
            return False

    async def _login(self, page: Page, creds: Credentials | None, ui: LoginUI, manual: bool = False) -> None:
        """Recorre el flujo de login como una máquina de estados tolerante a cambios de página."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.login_timeout_s
        mode = self.settings.login_mode
        counts = {"idp": 0, "local": 0, "email": 0, "password": 0, "code": 0, "proof": 0}

        if not await self._is_logged_in(page):
            await page.goto(self.url(S.LOGIN_PATH), wait_until="domcontentloaded")

        while loop.time() < deadline:
            if await self._is_logged_in(page):
                await ui.update("done")
                return

            if manual:
                # El usuario inicia sesión a mano en la ventana de Chromium del PC.
                await ui.update("manual")
                await page.wait_for_timeout(1000)
                continue

            if creds is None:
                raise MoodleAuthRequired("Hace falta iniciar sesión")

            # ---------------- páginas de Moodle -----------------------------
            if self._on_moodle(page):
                if counts["local"] and await self._visible(page, S.LOGIN_ERROR):
                    raise MoodleLoginError(await self._text(page, S.LOGIN_ERROR) or "Usuario o contraseña incorrectos")
                if mode != "moodle" and await self._visible(page, S.IDP_BUTTON):
                    if counts["idp"] >= 3:
                        raise MoodleLoginError("Moodle no completó el inicio de sesión con Microsoft")
                    counts["idp"] += 1
                    await ui.update("working", message="Abriendo el inicio de sesión de Microsoft…")
                    await self._click(page, S.IDP_BUTTON)
                elif mode != "microsoft" and await self._visible(page, S.LOGIN_PASSWORD):
                    if counts["local"] >= 2 or not creds.password:
                        raise MoodleAuthRequired("Introduce tu contraseña")
                    counts["local"] += 1
                    await page.locator(visible(S.LOGIN_USERNAME)).first.fill(creds.username)
                    await page.locator(visible(S.LOGIN_PASSWORD)).first.fill(creds.password)
                    await self._click(page, S.LOGIN_SUBMIT)
                elif mode == "microsoft" and S.LOGIN_PATH in page.url:
                    await page.wait_for_timeout(1500)
                    if S.LOGIN_PATH in page.url and not await self._visible(page, S.IDP_BUTTON):
                        raise MoodleLoginError(
                            "No se encontró el botón de Microsoft en Florida Oberta. "
                            "Revisa IDP_BUTTON en app/moodle/selectors.py"
                        )
                await page.wait_for_timeout(700)
                continue

            # ---------------- páginas de Microsoft --------------------------
            if await self._visible(page, S.MS_ERROR):
                msg = await self._text(page, S.MS_ERROR)
                if msg:
                    raise MoodleLoginError(msg)

            if await self._visible(page, S.MS_MFA_NUMBER):
                number = await self._text(page, S.MS_MFA_NUMBER)
                await ui.update("mfa_number", number=number,
                                message=f"Abre Microsoft Authenticator y escribe el número {number}")
            elif await self._visible(page, S.MS_MFA_CODE):
                if counts["code"] >= 3:
                    raise MoodleLoginError("Código de verificación rechazado varias veces")
                remaining = max(1.0, deadline - loop.time())
                code = await asyncio.wait_for(ui.request_code(), timeout=remaining)
                counts["code"] += 1
                await page.locator(visible(S.MS_MFA_CODE)).first.fill(code.strip())
                await self._click(page, S.MS_MFA_CODE_SUBMIT)
                await ui.update("working", message="Comprobando el código…")
            elif await self._visible(page, S.MS_MFA_PUSH):
                await ui.update("mfa_push", message="Aprueba el inicio de sesión en Microsoft Authenticator")
            elif await self._visible(page, S.MS_MFA_PROOFS) and counts["proof"] < 2:
                counts["proof"] += 1
                await page.locator(visible(S.MS_MFA_PROOFS)).first.click()
            elif await self._visible(page, S.MS_KMSI):
                await self._click(page, S.MS_KMSI_YES if self.settings.ms_stay_signed_in else S.MS_KMSI_NO)
            elif await self._visible(page, S.MS_OTHER_ACCOUNT):
                await self._click(page, S.MS_OTHER_ACCOUNT)
            elif await self._visible(page, S.MS_PASSWORD):
                if not creds.password:
                    raise MoodleAuthRequired("Introduce tu contraseña de Microsoft")
                if counts["password"] >= 2:
                    raise MoodleLoginError("Microsoft no aceptó la contraseña")
                counts["password"] += 1
                await ui.update("working", message="Enviando contraseña…")
                await page.locator(visible(S.MS_PASSWORD)).first.fill(creds.password)
                await self._click(page, S.MS_SUBMIT)
            elif await self._visible(page, S.MS_EMAIL):
                if counts["email"] >= 2:
                    raise MoodleLoginError("Microsoft no aceptó el usuario (¿correo institucional correcto?)")
                counts["email"] += 1
                await ui.update("working", message="Enviando usuario a Microsoft…")
                await page.locator(visible(S.MS_EMAIL)).first.fill(creds.username)
                await self._click(page, S.MS_SUBMIT)
            await page.wait_for_timeout(700)

        raise MoodleLoginError("Se agotó el tiempo para completar el inicio de sesión")

    # ------------------------------------------------------------ sesiones
    @asynccontextmanager
    async def session(self, creds: Credentials | None) -> AsyncIterator[Page]:
        """Página con sesión iniciada. Reintenta en silencio; si hace falta MFA, MoodleAuthRequired."""
        if self._interactive:
            raise MoodleBusy("Hay un inicio de sesión en curso; termínalo primero")
        async with self._lock:
            if not self.store.exists() and (creds is None or not creds.password):
                raise MoodleAuthRequired("Hace falta iniciar sesión")
            async with self._context() as context:
                page = await context.new_page()
                try:
                    await page.goto(self.url(S.DASHBOARD_PATH), wait_until="domcontentloaded")
                    if not await self._is_logged_in(page):
                        log.info("Sesión caducada: reintentando login en segundo plano")
                        if creds is None or not creds.password:
                            raise MoodleAuthRequired("La sesión ha caducado: vuelve a conectar")
                        await self._login(page, creds, SilentUI())
                    await self._save_state(context)
                    yield page
                    await self._save_state(context)
                except PlaywrightTimeout as exc:
                    raise MoodleError("Florida Oberta tardó demasiado en responder") from exc
                except PlaywrightError as exc:
                    log.warning("Error de navegador (%s)", type(exc).__name__)  # sin URLs ni datos personales
                    raise MoodleError("Error del navegador al hablar con Florida Oberta") from exc

    async def interactive_login(
        self, creds: Credentials | None, ui: LoginUI, manual: bool = False, fresh: bool = False
    ) -> dict:
        """Login acompañado desde la tablet (MFA) o manual en la ventana del PC."""
        if self._interactive:
            raise MoodleBusy("Ya hay un inicio de sesión en curso")
        self._interactive = True
        try:
            async with self._lock:
                if fresh:
                    self.store.clear()
                async with self._context(headless=False if manual else None, fresh=fresh) as context:
                    page = await context.new_page()
                    try:
                        await page.goto(self.url(S.DASHBOARD_PATH), wait_until="domcontentloaded")
                        await self._login(page, creds, ui, manual=manual)
                        await self._save_state(context)
                        name = await self._text(page, S.USER_FULLNAME) or None
                        return {"ok": True, "user": name}
                    except PlaywrightTimeout as exc:
                        raise MoodleError("Florida Oberta o Microsoft tardaron demasiado en responder") from exc
                    except PlaywrightError as exc:
                        log.warning("Error de navegador (%s)", type(exc).__name__)  # sin URLs ni datos personales
                        raise MoodleError("Error del navegador durante el inicio de sesión") from exc
        finally:
            self._interactive = False

    # ---------------------------------------------------------------- cursos
    async def list_courses(self, creds: Credentials | None) -> list[dict]:
        async with self.session(creds) as page:
            courses = None
            for classification in ("all", "allincludinghidden"):
                courses = await self._courses_via_ajax(page, classification)
                log.info("Cursos vía AJAX (%s): %s", classification, "error" if courses is None else len(courses))
                if courses:
                    return courses
            for path in (S.MY_COURSES_PATH, S.DASHBOARD_PATH):
                courses = await self._courses_via_dom(page, path)
                log.info("Cursos vía página %s: %d", path, len(courses))
                if courses:
                    return courses
            log.warning("No se encontró ningún curso (url actual: %s)", urlparse(page.url).path)
            return []

    async def _courses_via_ajax(self, page: Page, classification: str = "all") -> list[dict] | None:
        sesskey = await page.evaluate(S.JS_SESSKEY)
        if not sesskey:
            return None
        payload = [{
            "index": 0,
            "methodname": S.AJAX_COURSES_METHOD,
            "args": {"offset": 0, "limit": 0, "classification": classification, "sort": "fullname"},
        }]
        resp = await page.request.post(
            self.url(f"{S.AJAX_SERVICE_PATH}?sesskey={sesskey}&info={S.AJAX_COURSES_METHOD}"),
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        if not resp.ok:
            log.warning("AJAX de cursos: HTTP %s", resp.status)
            return None
        try:
            body = await resp.json()
            first = body[0]
        except (ValueError, KeyError, IndexError, TypeError):
            return None
        if first.get("error"):
            exc = first.get("exception") or {}
            log.warning("Moodle AJAX devolvió un error: %s", exc.get("errorcode") or exc.get("message"))
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

    async def _courses_via_dom(self, page: Page, path: str = S.MY_COURSES_PATH) -> list[dict]:
        await page.goto(self.url(path), wait_until="domcontentloaded")
        try:
            await page.locator(S.COURSE_LINK).first.wait_for(timeout=min(self.settings.timeout_ms, 15000))
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
