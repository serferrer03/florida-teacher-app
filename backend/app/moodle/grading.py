"""Fase 4: entregas y calificación de una tarea.

PRIVACIDAD: este módulo maneja datos personales del alumnado (nombre, estado de
entrega, archivos, nota). Nada se escribe en disco ni en los registros: se
devuelve a la tablet y se descarta. Solo se lee el nombre y el id interno de
Moodle (no correos ni otros campos de identidad).
"""
from __future__ import annotations

from playwright.async_api import Page

from . import selectors as S
from .assign import text_to_html
from .client import MoodleError

READ_PAGE_JS = """([sel, headers, exclude]) => {
  const table = document.querySelector(sel.table);
  if (!table) return null;
  const ths = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim().toLowerCase());
  const col = {};
  for (const [key, names] of Object.entries(headers)) {
    col[key] = ths.findIndex(t => names.some(n => t.includes(n)) && !exclude.some(x => key === 'grade' && t.includes(x)));
  }
  const cellText = (tr, i) => {
    if (i < 0) return '';
    const td = tr.children[i];
    return td ? td.innerText.replace(/\\s+/g, ' ').trim() : '';
  };
  return [...table.querySelectorAll(sel.row)].map(tr => {
    const link = tr.querySelector(sel.user);
    const box = tr.querySelector(sel.userid);
    let id = box ? Number(box.value) : NaN;
    if (!id && link) id = Number(new URL(link.href).searchParams.get('id'));
    if (!id) return null;
    const status = [...tr.querySelectorAll(sel.status)].map(e => e.textContent.trim()).filter(Boolean);
    return {
      userid: id,
      name: link ? link.textContent.trim() : '',
      status: [...new Set(status)],
      late: !!tr.querySelector('.latesubmission, .overdue'),
      submitted: !!tr.querySelector('.submissionstatussubmitted'),
      grade: cellText(tr, col.grade),
      modified: cellText(tr, col.modified),
      onlinetext: cellText(tr, col.onlinetext).slice(0, 2000),
      feedback: cellText(tr, col.feedback).slice(0, 2000),
      files: [...tr.querySelectorAll(sel.file)].map(a => ({ name: a.textContent.trim(), url: a.href })),
      onlinetext_url: (tr.querySelector(sel.onlinetext) || {}).href || null,
    };
  }).filter(Boolean);
}"""


async def list_submissions(page: Page, base: str, cmid: int) -> list[dict]:
    rows: dict[int, dict] = {}
    sel = {"table": S.GRADING_TABLE, "row": S.GRADING_ROW, "user": S.ROW_USER_LINK,
           "userid": S.ROW_USERID, "status": S.ROW_STATUS, "file": S.ROW_FILE_LINK,
           "onlinetext": S.ROW_ONLINETEXT_LINK}
    for n in range(100):  # la tabla está paginada; se recorren las páginas
        await page.goto(base + S.GRADING_PATH.format(cmid=cmid, page=n), wait_until="domcontentloaded")
        found = await page.evaluate(READ_PAGE_JS, [sel, S.COLUMN_HEADERS, S.COLUMN_HEADERS_EXCLUDE])
        if found is None:
            if n == 0:
                raise MoodleError("No se encontró la tabla de entregas (¿permisos de calificación en esta tarea?)")
            break
        new = [r for r in found if r["userid"] not in rows]
        if not new:
            break
        for r in new:
            rows[r["userid"]] = r
    return sorted(rows.values(), key=lambda r: r["name"].lower())


async def save_grade(page: Page, base: str, cmid: int, userid: int, grade: float | None,
                     feedback: str | None, notify: bool) -> None:
    await page.goto(base + S.GRADE_PATH.format(cmid=cmid, userid=userid), wait_until="domcontentloaded")
    if not await page.locator(S.SAVE_GRADE).count():
        raise MoodleError("No se encontró el formulario de calificación (SAVE_GRADE)")
    if grade is not None:
        field = page.locator(S.GRADE_INPUT).first
        if not await field.count():
            raise MoodleError("Esta tarea no tiene calificación numérica editable (GRADE_INPUT)")
        tag = await field.evaluate("e => e.tagName")
        if tag == "SELECT":
            raise MoodleError("Esta tarea usa una escala: califícala desde Florida Oberta")
        text = f"{grade:g}"
        if "." in text:  # separador decimal según el idioma de Moodle (es/ca/valencià usan coma)
            lang = (await page.evaluate("document.documentElement.lang") or "").lower()
            if lang[:2] in {"es", "ca", "va", "gl", "eu", "fr", "it", "pt", "de"}:
                text = text.replace(".", ",")
        await field.fill(text)
    if feedback is not None:
        ok = await page.evaluate(
            """([id, html]) => {
                 const tiny = window.tinyMCE && window.tinyMCE.get && window.tinyMCE.get(id);
                 if (tiny) { tiny.setContent(html); tiny.save(); }
                 const atto = document.getElementById(id + 'editable'); if (atto) atto.innerHTML = html;
                 const ta = document.getElementById(id); if (!ta) return false;
                 ta.value = html; return true;
               }""",
            [S.FEEDBACK_EDITOR, text_to_html(feedback)],
        )
        if not ok:
            raise MoodleError("No se encontró el campo de comentarios de retroalimentación")
    box = page.locator(S.NOTIFY_STUDENT).first
    if await box.count():
        if await box.evaluate("e => e.tagName") == "SELECT":
            await box.select_option("1" if notify else "0")
        else:
            await box.set_checked(notify)
    async with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
        await page.locator(S.SAVE_GRADE).first.click()
    errors = await page.evaluate(
        "(sel) => [...document.querySelectorAll(sel)].map(e => e.textContent.trim()).filter(Boolean)",
        "[id^='id_error_'], .invalid-feedback:not(:empty), .alert-danger")
    if errors:
        raise MoodleError("Moodle no guardó la calificación: " + "; ".join(dict.fromkeys(errors)))


async def full_onlinetext(page: Page, base: str, url: str) -> str:
    """Texto en línea completo (la tabla solo muestra un resumen)."""
    if not url.startswith(base + "/mod/assign/"):
        return ""
    await page.goto(url, wait_until="domcontentloaded")
    el = page.locator(S.ONLINETEXT_FULL).first
    return (await el.inner_text()).strip() if await el.count() else ""


async def fetch_file(page: Page, base: str, url: str) -> tuple[bytes, str]:
    if not url.startswith(base + "/pluginfile.php/"):
        raise MoodleError("Dirección de archivo no permitida")
    resp = await page.request.get(url)
    if not resp.ok:
        raise MoodleError(f"Florida Oberta no entregó el archivo ({resp.status})")
    return await resp.body(), resp.headers.get("content-type", "application/octet-stream")
