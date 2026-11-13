"""Actualiza la hoja de Google del profesor mediante un Apps Script propio.

El profesor pega `integraciones/google-sheets.gs` en su hoja (Extensiones →
Apps Script), define un secreto y lo publica como aplicación web. La app envía
filas (curso, tarea, alumno, nota, observación, estado) que el script inserta o
actualiza. No hace falta dar a esta app acceso a toda la cuenta de Google.
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)


def configured() -> bool:
    return bool(os.environ.get("GOOGLE_SHEETS_WEBHOOK_URL") and os.environ.get("GOOGLE_SHEETS_SECRET"))


async def push(rows: list[dict]) -> str | None:
    """Envía filas; devuelve un mensaje de error o None si fue bien (o no está configurado)."""
    if not configured() or not rows:
        return None
    url = os.environ["GOOGLE_SHEETS_WEBHOOK_URL"]
    if not url.startswith("https://script.google.com/"):
        return "GOOGLE_SHEETS_WEBHOOK_URL debe ser una URL de Apps Script (https://script.google.com/...)"
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            r = await client.post(url, json={"secret": os.environ["GOOGLE_SHEETS_SECRET"], "rows": rows})
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("No se pudo actualizar la hoja de Google (%s)", type(exc).__name__)
        return "No se pudo contactar con la hoja de Google"
    if not data.get("ok"):
        return f"La hoja de Google rechazó los datos: {data.get('error', 'error desconocido')}"
    log.info("Hoja de Google actualizada: %d filas", len(rows))
    return None
