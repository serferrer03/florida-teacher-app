"""Capa común de IA: el resto de la app habla con «la IA» sin saber si es Claude o Gemini.

Partes neutras: {"kind": "text", "text": ...} | {"kind": "pdf", "data": bytes, "title": ...}
              | {"kind": "image", "mime": "image/png", "data": bytes}
generate_json() devuelve un dict que cumple el esquema JSON pedido.
"""
from __future__ import annotations

import base64
import json
import logging

from . import settings_store

log = logging.getLogger(__name__)

CLAUDE_DEFAULT = "claude-opus-5-5"
GEMINI_DEFAULT = "gemini-3.8-flash"


class AIError(Exception):
    """La IA no está configurada o no pudo responder."""


class AIRefused(AIError):
    """La IA declinó la petición."""


def provider() -> str | None:
    """Proveedor activo según los ajustes y las claves disponibles."""
    pref = (settings_store.get("ai_provider") or "auto").lower()
    has_claude = bool(settings_store.get("anthropic_api_key"))
    has_gemini = bool(settings_store.get("gemini_api_key"))
    if pref == "claude":
        return "claude" if has_claude else None
    if pref == "gemini":
        return "gemini" if has_gemini else None
    return "claude" if has_claude else "gemini" if has_gemini else None


def configured() -> bool:
    return provider() is not None


def model_name() -> str:
    p = provider()
    custom = settings_store.get("ai_model")
    if custom and p and custom.startswith(p if p == "gemini" else "claude"):
        return custom
    return GEMINI_DEFAULT if p == "gemini" else CLAUDE_DEFAULT


async def generate_json(system: str, parts: list[dict], schema: dict, max_tokens: int = 16000) -> dict:
    p = provider()
    if p is None:
        raise AIError("No hay ninguna clave de IA configurada (Ajustes → Inteligencia artificial)")
    if p == "claude":
        return await _claude(system, parts, schema, max_tokens)
    return await _gemini(system, parts, schema)


async def _claude(system: str, parts: list[dict], schema: dict, max_tokens: int) -> dict:
    import anthropic

    blocks: list[dict] = []
    for part in parts:
        if part["kind"] == "text":
            blocks.append({"type": "text", "text": part["text"]})
        elif part["kind"] == "pdf":
            blocks.append({"type": "document", "title": part.get("title", "documento.pdf"), "source": {
                "type": "base64", "media_type": "application/pdf",
                "data": base64.standard_b64encode(part["data"]).decode()}})
        elif part["kind"] == "image":
            blocks.append({"type": "image", "source": {
                "type": "base64", "media_type": part["mime"], "data": base64.standard_b64encode(part["data"]).decode()}})
    client = anthropic.AsyncAnthropic(api_key=settings_store.get("anthropic_api_key"))
    try:
        response = await client.beta.messages.create(
            model=model_name(),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": blocks}],
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as exc:
        raise AIError("La clave de la API de Claude no es válida") from exc
    except anthropic.RateLimitError as exc:
        raise AIError("Límite de uso de la API de Claude alcanzado; inténtalo más tarde") from exc
    except anthropic.BadRequestError as exc:
        raise AIError(f"Claude no pudo procesar la petición: {exc.message[:200]}") from exc
    except anthropic.APIStatusError as exc:
        raise AIError(f"Error de la API de Claude ({exc.status_code})") from exc
    except anthropic.APIConnectionError as exc:
        raise AIError("No se pudo conectar con la API de Claude") from exc
    if response.stop_reason == "refusal":
        raise AIRefused("La IA declinó esta petición")
    if response.stop_reason == "max_tokens":
        raise AIError("La respuesta de la IA quedó incompleta")
    text = next((b.text for b in response.content if b.type == "text"), "")
    return _parse(text)


async def _gemini(system: str, parts: list[dict], schema: dict) -> dict:
    from google import genai
    from google.genai import errors, types

    contents = []
    for part in parts:
        if part["kind"] == "text":
            contents.append(types.Part.from_text(text=part["text"]))
        elif part["kind"] == "pdf":
            contents.append(types.Part.from_bytes(data=part["data"], mime_type="application/pdf"))
        elif part["kind"] == "image":
            contents.append(types.Part.from_bytes(data=part["data"], mime_type=part["mime"]))
    client = genai.Client(api_key=settings_store.get("gemini_api_key"))
    try:
        response = await client.aio.models.generate_content(
            model=model_name(),
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=schema,
            ),
        )
    except errors.ClientError as exc:
        code = getattr(exc, "code", None)
        if code in (401, 403):
            raise AIError("La clave de la API de Gemini no es válida") from exc
        if code == 429:
            raise AIError("Límite de uso de la API de Gemini alcanzado; inténtalo más tarde") from exc
        raise AIError(f"Gemini no pudo procesar la petición ({code})") from exc
    except errors.APIError as exc:
        raise AIError("Error de la API de Gemini") from exc
    text = response.text or ""
    if not text:
        raise AIRefused("La IA no devolvió respuesta (posible bloqueo de seguridad)")
    return _parse(text)


def _parse(text: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise AIError("La IA devolvió una respuesta no válida") from exc
    if not isinstance(data, dict):
        raise AIError("La IA devolvió una respuesta no válida")
    return data


async def test() -> str:
    """Prueba rápida de la clave configurada."""
    data = await generate_json("Responde solo con el JSON pedido.", [{"kind": "text", "text": "Di 'ok'."}],
                               {"type": "object", "properties": {"ok": {"type": "string"}},
                                "required": ["ok"], "additionalProperties": False}, max_tokens=2000)
    return f"{provider()} · {model_name()} · respuesta: {data.get('ok', '')}"
