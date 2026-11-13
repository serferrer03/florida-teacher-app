"""Fase 3: contenidos del curso (temas, recursos y actividades).

Lectura con core_courseformat_get_state (Moodle 4.x) y, si no existe, leyendo
la página del curso. Los cambios usan las mismas llamadas AJAX que el modo
edición de Moodle; los recursos nuevos, el formulario estándar (modedit.php).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from playwright.async_api import Page

from . import selectors as S
from .assign import attach_files, open_add_form, submit_form, text_to_html
from .client import MoodleError

log = logging.getLogger(__name__)


class AjaxError(MoodleError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def ajax(page: Page, base: str, method: str, args: dict):
    sesskey = await page.evaluate(S.JS_SESSKEY)
    if not sesskey:
        raise MoodleError("Sesión de Moodle sin sesskey")
    resp = await page.request.post(
        f"{base}{S.AJAX_SERVICE_PATH}?sesskey={sesskey}&info={method}",
        data=json.dumps([{"index": 0, "methodname": method, "args": args}]),
        headers={"Content-Type": "application/json"},
    )
    try:
        first = (await resp.json())[0]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AjaxError("badresponse", f"Respuesta inesperada de Moodle ({resp.status})") from exc
    if first.get("error"):
        exc = first.get("exception") or {}
        raise AjaxError(exc.get("errorcode") or "error", exc.get("message") or "Moodle devolvió un error")
    return first.get("data")


async def read_contents(page: Page, base: str, course_id: int) -> list[dict]:
    await page.goto(f"{base}/course/view.php?id={course_id}", wait_until="domcontentloaded")
    try:
        raw = await ajax(page, base, S.AJAX_COURSE_STATE, {"courseid": course_id})
        state = json.loads(raw) if isinstance(raw, str) else raw
        return _from_state(state, base)
    except AjaxError as exc:
        log.warning("get_state no disponible (%s): leyendo la página del curso", exc.code)
        return await _from_page(page)


def _from_state(state: dict, base: str) -> list[dict]:
    cms = {int(c["id"]): c for c in state.get("cm", [])}
    out = []
    for s in sorted(state.get("section", []), key=lambda s: s.get("number", s.get("section", 0))):
        items = []
        for cmid in s.get("cmlist", []):
            c = cms.get(int(cmid))
            if not c:
                continue
            mod = c.get("module") or c.get("modname") or "?"
            items.append({
                "cmid": int(c["id"]), "name": c.get("name", ""), "modname": mod,
                "visible": bool(c.get("visible", True)),
                "url": c.get("url") or f"{base}/mod/{mod}/view.php?id={c['id']}",
            })
        num = s.get("number", s.get("section", 0))
        out.append({
            "id": int(s["id"]), "number": int(num),
            "name": s.get("title") or s.get("rawtitle") or f"Tema {num}",
            "visible": bool(s.get("visible", True)), "items": items,
        })
    return out


async def _from_page(page: Page) -> list[dict]:
    """Alternativa sin AJAX (Moodle 3.x): solo lectura básica de la página."""
    return await page.evaluate(
        """([secSel, nameSel]) => [...document.querySelectorAll(secSel)].map(li => {
             const num = Number(li.id.replace('section-', ''));
             const t = li.querySelector(nameSel);
             const items = [...li.querySelectorAll('li.activity[id^="module-"]')].map(a => {
               const link = a.querySelector('a[href*="/mod/"]');
               const m = (a.className.match(/modtype_([a-z0-9_]+)/) || [])[1] || '?';
               const name = a.querySelector('.instancename, .activityname, [data-activityname]');
               return { cmid: Number(a.id.replace('module-', '')), modname: m,
                        name: (name ? (name.dataset.activityname || name.firstChild.textContent) : '').trim(),
                        visible: !a.querySelector('.dimmed, .badge.bg-secondary') && !a.classList.contains('hiddenactivity'),
                        url: link ? link.href : '' };
             });
             return { id: Number(li.dataset.id || li.dataset.sectionid || 0), number: num,
                      name: (t ? t.textContent : 'Tema ' + num).trim(),
                      visible: !li.classList.contains('hidden'), items };
           })""",
        [S.COURSE_SECTION, S.COURSE_SECTION_NAME],
    )


async def set_visibility(page: Page, base: str, course_id: int, kind: str, item_id: int, visible: bool) -> None:
    await page.goto(f"{base}/course/view.php?id={course_id}", wait_until="domcontentloaded")
    action = f"{kind}_{'show' if visible else 'hide'}"
    try:
        await ajax(page, base, S.AJAX_COURSE_UPDATE, {"action": action, "courseid": course_id, "ids": [item_id]})
        return
    except AjaxError as first:
        log.warning("update_course falló (%s): probando la llamada antigua", first.code)
        method = S.AJAX_EDIT_MODULE if kind == "cm" else S.AJAX_EDIT_SECTION
        try:
            await ajax(page, base, method, {"action": "show" if visible else "hide", "id": item_id, "sectionreturn": 0})
        except AjaxError:
            raise first from None


async def rename(page: Page, base: str, course_id: int, kind: str, item_id: int, name: str) -> None:
    await page.goto(f"{base}/course/view.php?id={course_id}", wait_until="domcontentloaded")
    if kind == "cm":
        component, itemtype = "core_course", "activityname"
    else:
        component, itemtype = f"format_{await page.evaluate(S.JS_COURSE_FORMAT)}", "sectionname"
    await ajax(page, base, S.AJAX_INPLACE,
               {"component": component, "itemtype": itemtype, "itemid": item_id, "value": name})


async def add_resource(page: Page, base: str, course_id: int, values: dict, files: list[Path]) -> None:
    """values: type ('file'|'url'), name, description, section, visible, url."""
    mod = "resource" if values["type"] == "file" else "url"
    await open_add_form(page, base, course_id, values["section"], mod)
    f = S.RESOURCE_FIELDS
    missing = await page.evaluate(
        """([f, v, urlId]) => {
             const miss = [];
             const set = (id, val) => { const el = document.getElementById(id); if (!el) return false;
               el.disabled = false; el.value = String(val); el.dispatchEvent(new Event('change', {bubbles: true})); return true; };
             if (!set(f.name, v.name)) miss.push('nombre');
             const tiny = window.tinyMCE && window.tinyMCE.get && window.tinyMCE.get(f.intro);
             if (tiny) { tiny.setContent(v.intro_html); tiny.save(); }
             const atto = document.getElementById(f.intro + 'editable'); if (atto) atto.innerHTML = v.intro_html;
             set(f.intro, v.intro_html);
             const sd = document.getElementById(f.showdescription);
             if (sd && sd.checked !== !!v.show_description) sd.click();
             if (!set(f.visible, v.visible ? 1 : 0)) miss.push('visibilidad');
             if (v.type === 'url' && !set(urlId, v.url)) miss.push('dirección URL');
             return miss;
           }""",
        [f, {**values, "intro_html": text_to_html(values.get("description", ""))}, S.URL_FIELD],
    )
    if missing:
        raise MoodleError("No se pudieron rellenar estos campos: " + ", ".join(missing))
    if mod == "resource":
        await attach_files(page, files, field=S.RESOURCE_FILES_FIELD)
    await submit_form(page, S.RETURN_TO_COURSE_SUBMIT, "/course/view.php")
