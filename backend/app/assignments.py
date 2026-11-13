"""Fase 2: validación de la tarea que llega de la tablet y conversión a Moodle."""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from .moodle.assign import text_to_html

LOCAL_DT = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$"  # <input type="datetime-local">


class GradeCondition(BaseModel):
    item_id: int
    min_percent: float = Field(ge=0, le=100)


class Restrictions(BaseModel):
    date_from: str | None = Field(default=None, pattern=LOCAL_DT)
    date_until: str | None = Field(default=None, pattern=LOCAL_DT)
    group_ids: list[int] = Field(default_factory=list, max_length=50)
    grouping_id: int | None = None
    grade: GradeCondition | None = None
    show_to_students: bool = True

    def is_empty(self) -> bool:
        return not (self.date_from or self.date_until or self.group_ids or self.grouping_id or self.grade)


class AssignmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=20000)
    show_description: bool = False
    section: int = Field(default=0, ge=0, le=1000)
    visible: bool = True
    allow_from: str | None = Field(default=None, pattern=LOCAL_DT)
    due: str | None = Field(default=None, pattern=LOCAL_DT)
    cutoff: str | None = Field(default=None, pattern=LOCAL_DT)
    grading_due: str | None = Field(default=None, pattern=LOCAL_DT)
    online_text: bool = False
    file_submissions: bool = True
    max_files: int = Field(default=1, ge=1, le=100)
    max_size_bytes: int = Field(default=0, ge=0)
    grade_max: int = Field(default=10, ge=0, le=10000)
    restrictions: Restrictions = Field(default_factory=Restrictions)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v).strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        return v

    @model_validator(mode="after")
    def check_dates(self) -> "AssignmentIn":
        # Las cadenas YYYY-MM-DDTHH:MM se comparan bien como texto
        if self.allow_from and self.due and self.due < self.allow_from:
            raise ValueError("La fecha de entrega es anterior a «Permitir entregas desde»")
        if self.cutoff and self.due and self.cutoff < self.due:
            raise ValueError("La fecha límite es anterior a la fecha de entrega")
        if self.grading_due and self.due and self.grading_due < self.due:
            raise ValueError("«Recordarme calificar» es anterior a la fecha de entrega")
        r = self.restrictions
        if r.date_from and r.date_until and r.date_until <= r.date_from:
            raise ValueError("En las restricciones, «hasta» debe ser posterior a «desde»")
        if not (self.online_text or self.file_submissions):
            raise ValueError("Elige al menos un tipo de entrega (texto en línea o archivos)")
        return self


def _parts(local: str | None) -> dict | None:
    if not local:
        return None
    d = datetime.fromisoformat(local)
    return {"y": d.year, "m": d.month, "d": d.day, "h": d.hour, "i": d.minute}


def _epoch(local: str) -> int:
    return int(datetime.fromisoformat(local).astimezone().timestamp())  # zona horaria del PC


def availability_json(r: Restrictions) -> dict | None:
    """JSON de core_availability (el mismo que guarda «Restricciones de acceso»)."""
    if r.is_empty():
        return None
    conds: list[dict] = []
    if r.date_from:
        conds.append({"type": "date", "d": ">=", "t": _epoch(r.date_from)})
    if r.date_until:
        conds.append({"type": "date", "d": "<", "t": _epoch(r.date_until)})
    if r.grade:
        conds.append({"type": "grade", "id": r.grade.item_id, "min": r.grade.min_percent})
    if r.grouping_id:
        conds.append({"type": "grouping", "id": r.grouping_id})
    if len(r.group_ids) == 1:
        conds.append({"type": "group", "id": r.group_ids[0]})
    elif r.group_ids:  # varios grupos: el alumno debe estar en CUALQUIERA de ellos
        conds.append({"op": "|", "c": [{"type": "group", "id": g} for g in r.group_ids]})
    show = r.show_to_students
    return {"op": "&", "c": conds, "showc": [show] * len(conds)}


def to_form_values(a: AssignmentIn) -> dict:
    return {
        "name": a.name,
        "intro_html": text_to_html(a.description),
        "show_description": a.show_description,
        "section": a.section,
        "visible": a.visible,
        "dates": {k: _parts(getattr(a, k)) for k in ("allow_from", "due", "cutoff", "grading_due")},
        "online_text": a.online_text,
        "file_submissions": a.file_submissions,
        "max_files": a.max_files,
        "max_size_bytes": a.max_size_bytes,
        "grade_max": a.grade_max,
        "availability": availability_json(a.restrictions),
    }
