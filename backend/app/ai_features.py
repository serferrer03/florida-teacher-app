"""Automatizaciones con IA para el profesor (sin datos del alumnado).

- draft_assignment: de una descripción en lenguaje natural a una tarea completa.
- rubric: criterios de evaluación para la evaluación automática.
- improve_feedback: mejora la redacción de un comentario para el alumno.
"""
from __future__ import annotations

from . import ai

SYSTEM = ("Eres un asistente para un profesor de Florida Universitària (formación profesional y universidad, "
          "España). Escribes en español claro y profesional. Responde solo con el JSON pedido.")

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Título breve de la tarea (máx. 80 caracteres)"},
        "description": {"type": "string", "description": "Enunciado para el alumnado: objetivo, qué entregar, formato y pasos. Texto plano con párrafos."},
        "criteria": {"type": "string", "description": "Rúbrica con criterios y puntos que suman la nota máxima"},
        "grade_max": {"type": "number"},
        "online_text": {"type": "boolean", "description": "Si la entrega es texto escrito en la plataforma"},
        "file_submissions": {"type": "boolean", "description": "Si la entrega son archivos"},
        "max_files": {"type": "integer"},
        "due_in_days": {"type": "integer", "description": "Días desde hoy hasta la entrega (si el profesor lo indica; si no, 7)"},
        "due_time": {"type": "string", "description": "Hora de entrega HH:MM (por defecto 23:55)"},
    },
    "required": ["name", "description", "criteria", "grade_max", "online_text", "file_submissions",
                 "max_files", "due_in_days", "due_time"],
    "additionalProperties": False,
}


async def draft_assignment(prompt: str, course: str, today: str) -> dict:
    data = await ai.generate_json(SYSTEM, [{"kind": "text", "text": (
        f"Curso: {course}\nHoy es {today}.\nEl profesor quiere crear esta tarea:\n{prompt}\n\n"
        "Redacta la tarea completa. Si el profesor no dice nota máxima usa 10. Si no dice el tipo de "
        "entrega, deduce el más adecuado (archivos para código, documentos o imágenes). Interpreta "
        "fechas relativas («el viernes», «en dos semanas») respecto a hoy.")}], DRAFT_SCHEMA, max_tokens=8000)
    data["grade_max"] = max(1, min(float(data["grade_max"]), 100))
    data["max_files"] = max(1, min(int(data["max_files"]), 20))
    data["due_in_days"] = max(0, min(int(data["due_in_days"]), 365))
    if not data["online_text"] and not data["file_submissions"]:
        data["file_submissions"] = True
    return data


async def rubric(name: str, description: str, grade_max: float) -> str:
    data = await ai.generate_json(SYSTEM, [{"kind": "text", "text": (
        f"Tarea: {name}\nEnunciado:\n{description or '(sin enunciado)'}\nNota máxima: {grade_max:g}\n\n"
        "Escribe una rúbrica clara para evaluar esta tarea: 3-6 criterios con su puntuación (que sumen la "
        "nota máxima) y qué se espera en cada uno. Incluye penalizaciones razonables (entrega incompleta, "
        "plagio evidente).")}],
        {"type": "object", "properties": {"criteria": {"type": "string"}}, "required": ["criteria"],
         "additionalProperties": False}, max_tokens=6000)
    return data["criteria"].strip()


async def improve_feedback(text: str, grade: str | None) -> str:
    data = await ai.generate_json(SYSTEM, [{"kind": "text", "text": (
        f"Comentario del profesor para un alumno{f' (nota: {grade})' if grade else ''}:\n{text}\n\n"
        "Mejora la redacción: respetuoso, constructivo y concreto (qué está bien, qué mejorar y cómo). "
        "Mantén el sentido y la severidad del profesor; no inventes hechos. Máximo 8 frases.")}],
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"],
         "additionalProperties": False}, max_tokens=4000)
    return data["text"].strip()
