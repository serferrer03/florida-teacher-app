"""Fase 2: crear tareas (mod/assign) rellenando el formulario estándar de Moodle.

Los campos se rellenan por id (ver ASSIGN_FIELDS/ASSIGN_DATES en selectors.py)
con JavaScript, porque muchos están en secciones plegadas. Los archivos se suben
con el selector de archivos de Moodle, como lo haría una persona.
"""
from __future__ import annotations

import html
import logging
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

from . import selectors as S
from .client import MoodleError, visible

log = logging.getLogger(__name__)

FILL_JS = """(args) => {
  const { f, dates, v } = args;
  const byId = (id) => document.getElementById(id);
  const missing = [];
  const fire = (el) => { el.dispatchEvent(new Event('change', { bubbles: true })); };
  const setVal = (id, val) => {
    const el = byId(id);
    if (!el) return false;
    el.disabled = false;
    if (el.tagName === 'SELECT' && ![...el.options].some(o => o.value === String(val))) return false;
    el.value = String(val); fire(el); return true;
  };
  const setCheck = (id, on) => {
    const el = byId(id);
    if (!el) return false;
    if (el.checked !== on) el.click();
    return true;
  };
  const setNearest = (id, val) => {          // minutos: opción más cercana por debajo
    const el = byId(id);
    if (!el) return false;
    const opts = [...el.options].map(o => Number(o.value)).filter(n => n <= val);
    if (!opts.length) return false;
    el.disabled = false; el.value = String(Math.max(...opts)); fire(el); return true;
  };

  if (!setVal(f.name, v.name)) missing.push('nombre');

  // Descripción: TinyMCE (Moodle 4.3+), Atto o textarea simple
  const tiny = window.tinyMCE && window.tinyMCE.get && window.tinyMCE.get(f.intro);
  if (tiny) { tiny.setContent(v.intro_html); tiny.save(); }
  const atto = byId(f.intro + 'editable');
  if (atto) atto.innerHTML = v.intro_html;
  if (!setVal(f.intro, v.intro_html)) missing.push('descripción');
  setCheck(f.showdescription, !!v.show_description);
  if (!setVal(f.visible, v.visible ? 1 : 0)) missing.push('visibilidad');

  for (const [key, base] of Object.entries(dates)) {
    const d = v.dates[key];
    if (!byId(`id_${base}_enabled`)) { if (d) missing.push(base); continue; }
    setCheck(`id_${base}_enabled`, !!d);
    if (!d) continue;
    const ok = setVal(`id_${base}_year`, d.y) & setVal(`id_${base}_month`, d.m) & setVal(`id_${base}_day`, d.d)
      & setVal(`id_${base}_hour`, d.h) & setNearest(`id_${base}_minute`, d.i);
    if (!ok) missing.push(base);
  }

  if (!setCheck(f.onlinetext, !!v.online_text) && v.online_text) missing.push('texto en línea');
  if (!setCheck(f.file, !!v.file_submissions) && v.file_submissions) missing.push('envío de archivos');
  if (v.file_submissions) {
    if (!setVal(f.maxfiles, v.max_files)) missing.push('nº máximo de archivos');
    if (!setVal(f.maxsize, v.max_size_bytes)) missing.push('tamaño máximo');
  }

  if (v.grade_max > 0) {
    setVal(f.grade_type, 'point');
    if (!setVal(f.grade_point, v.grade_max)) missing.push('calificación');
  } else if (!setVal(f.grade_type, 'none')) missing.push('sin calificación');

  if (v.availability) {
    const ta = byId(f.availability);
    if (!ta) missing.push('restricciones de acceso');
    else {
      const json = JSON.stringify(v.availability);
      ta.value = json;
      try {  // reconstruir el editor de restricciones con los nuevos datos
        const F = window.M.core_availability.form;
        F.rootList.node.remove();
        F.rootList = new window.M.core_availability.List(v.availability, true);
        F.mainDiv.appendChild(F.rootList.node);
        F.update(); F.rootList.renumber();
      } catch (e) { /* sin editor: basta con el JSON */ }
      try {
        if (JSON.parse(ta.value).c.length !== v.availability.c.length) ta.value = json;
      } catch (e) { ta.value = json; }
    }
  }
  return missing;
}"""


def text_to_html(text: str) -> str:
    """Texto plano de la tablet -> HTML seguro para la descripción."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return "".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs)


async def read_sections(page: Page, base: str, course_id: int) -> list[dict]:
    await page.goto(f"{base}/course/view.php?id={course_id}", wait_until="domcontentloaded")
    sections = await page.evaluate(
        """([itemSel, nameSel]) => [...document.querySelectorAll(itemSel)].map(li => {
             const n = Number((li.id || '').replace('section-', ''));
             const t = li.querySelector(nameSel);
             return { number: n, name: (t ? t.textContent : '').trim().replace(/\\s+/g, ' ') };
           }).filter(s => Number.isInteger(s.number))""",
        [S.COURSE_SECTION, S.COURSE_SECTION_NAME],
    )
    seen, out = set(), []
    for s in sections:
        if s["number"] not in seen:
            seen.add(s["number"])
            out.append({"number": s["number"], "name": s["name"] or f"Tema {s['number']}"})
    return out or [{"number": 0, "name": "General"}]


async def open_add_form(page: Page, base: str, course_id: int, section: int) -> None:
    await page.goto(base + S.ASSIGN_ADD_PATH.format(course=course_id, section=section),
                    wait_until="domcontentloaded")
    try:
        await page.locator(S.MODEDIT_FORM).first.wait_for(timeout=20000)
    except PlaywrightTimeout as exc:
        raise MoodleError("No se pudo abrir el formulario de nueva tarea (¿permisos de edición en el curso?)") from exc
    if not await page.locator(f"#{S.ASSIGN_FIELDS['name']}").count():
        raise MoodleError("El formulario de tarea no tiene el aspecto esperado; revisa ASSIGN_FIELDS en selectors.py")


async def read_form_options(page: Page) -> dict:
    avail = await page.evaluate(S.JS_AVAILABILITY_OPTIONS)
    selects = await page.evaluate(
        """(ids) => Object.fromEntries(ids.map(id => {
             const el = document.getElementById(id);
             return [id, el ? [...el.options].map(o => ({ value: o.value, label: o.textContent.trim() })) : []];
           }))""",
        [S.ASSIGN_FIELDS["maxfiles"], S.ASSIGN_FIELDS["maxsize"]],
    )
    clean = lambda items: [{"id": int(i["id"]), "name": str(i.get("name", ""))} for i in items if "id" in i]  # noqa: E731
    return {
        "restrictions_enabled": avail["enabled"],
        "groups": clean(avail["groups"]),
        "groupings": clean(avail["groupings"]),
        "grade_items": clean(avail["grades"]),
        "max_files": [o["value"] for o in selects[S.ASSIGN_FIELDS["maxfiles"]]],
        "max_sizes": selects[S.ASSIGN_FIELDS["maxsize"]],
    }


async def attach_files(page: Page, files: list[Path]) -> None:
    for path in files:
        before = await page.locator(S.ATTACH_FILENAME).count()
        add = page.locator(visible(S.ATTACH_ADD)).first
        if not await add.count():
            raise MoodleError("No se encontró «Archivos adicionales» en el formulario (ATTACH_ADD)")
        await add.click()
        dialog = page.locator(visible(S.PICKER_DIALOG)).first
        await dialog.wait_for(timeout=15000)
        repo = dialog.locator(visible(S.PICKER_UPLOAD_REPO)).first
        if await repo.count():
            await repo.click()
        await dialog.locator(S.PICKER_FILE_INPUT).first.set_input_files(str(path))
        await dialog.locator(visible(S.PICKER_UPLOAD_BTN)).first.click()
        try:
            await page.wait_for_function(
                "([sel, n]) => document.querySelectorAll(sel).length > n",
                arg=[S.ATTACH_FILENAME, before], timeout=120000,
            )
        except PlaywrightTimeout as exc:
            err = page.locator(visible(S.PICKER_ERROR)).first
            msg = (await err.inner_text()).strip() if await err.count() else "tiempo agotado"
            raise MoodleError(f"No se pudo subir «{path.name}»: {msg}") from exc
        log.info("Archivo adjuntado (%d de %d)", files.index(path) + 1, len(files))


async def submit(page: Page) -> int:
    async with page.expect_navigation(wait_until="domcontentloaded", timeout=120000):
        await page.locator(S.ASSIGN_SUBMIT).first.click()
    if "/mod/assign/view.php" in page.url:
        ids = parse_qs(urlparse(page.url).query).get("id")
        if ids and ids[0].isdigit():
            return int(ids[0])
    errors = await page.evaluate(
        """(sel) => [...document.querySelectorAll(sel)]
             .map(e => e.textContent.trim()).filter(t => t && t.length < 300)""",
        S.FORM_ERRORS,
    )
    detail = "; ".join(dict.fromkeys(errors)) or "Moodle no confirmó la creación"
    raise MoodleError(f"Moodle rechazó la tarea: {detail}")
