"""Fase 5: calendario mensual de Florida Oberta (fechas de entrega, cuestionarios...)."""
from __future__ import annotations

from playwright.async_api import Page

from . import selectors as S
from .contents import ajax


async def month_events(page: Page, base: str, year: int, month: int) -> list[dict]:
    await page.goto(f"{base}{S.DASHBOARD_PATH}", wait_until="domcontentloaded")
    data = await ajax(page, base, S.AJAX_CALENDAR_MONTH, {
        "year": year, "month": month, "courseid": 1, "categoryid": 0,
        "includenavigation": False, "mini": False, "day": 1,
    })
    seen, out = set(), []
    for week in (data or {}).get("weeks", []):
        for day in week.get("days", []):
            for e in day.get("events", []):
                if e.get("id") in seen:
                    continue
                seen.add(e.get("id"))
                course = e.get("course") or {}
                out.append({
                    "id": e.get("id"),
                    "name": e.get("name") or e.get("popupname") or "",
                    "start": int(e.get("timestart") or 0),
                    "course": course.get("fullname") or course.get("shortname"),
                    "course_id": course.get("id"),
                    "modname": e.get("modulename"),
                    "type": e.get("normalisedeventtype") or e.get("eventtype"),
                    "url": e.get("url") or e.get("viewurl"),
                })
    return sorted(out, key=lambda e: e["start"])
