"""Ajustes que el profesor cambia desde la app (pantalla «Ajustes»).

Las claves (API de IA, secreto de la hoja de Google) se guardan CIFRADAS en la
base de datos local. Si no hay valor en la app, se usa el de backend/.env.
La API nunca devuelve una clave: solo si está configurada y sus 4 últimos caracteres.
"""
from __future__ import annotations

import os

from .crypto import CredentialCipher
from .db import Database

# nombre -> (variable de entorno equivalente, ¿es secreto?)
FIELDS = {
    "ai_provider": ("AI_PROVIDER", False),          # auto | claude | gemini
    "anthropic_api_key": ("ANTHROPIC_API_KEY", True),
    "gemini_api_key": ("GEMINI_API_KEY", True),
    "ai_model": ("AI_MODEL", False),                # vacío = modelo recomendado del proveedor
    "sheets_url": ("GOOGLE_SHEETS_WEBHOOK_URL", False),
    "sheets_secret": ("GOOGLE_SHEETS_SECRET", True),
}


class Settings:
    def __init__(self, db: Database, cipher: CredentialCipher) -> None:
        self.db, self.cipher = db, cipher

    def get(self, name: str) -> str:
        env, secret = FIELDS[name]
        raw = self.db.get_meta(f"setting:{name}")
        if raw:
            if not secret:
                return raw
            try:
                return self.cipher.decrypt(bytes.fromhex(raw))
            except ValueError:
                return ""
        if name == "ai_model":
            return os.environ.get("AUTO_EVAL_MODEL") or os.environ.get(env, "")
        return os.environ.get(env, "")

    def set(self, name: str, value: str | None) -> None:
        if value is None:
            return
        _, secret = FIELDS[name]
        value = value.strip()
        self.db.set_meta(f"setting:{name}",
                         (self.cipher.encrypt(value).hex() if value else "") if secret else value)

    def public(self) -> dict:
        out = {}
        for name, (_, secret) in FIELDS.items():
            v = self.get(name)
            out[name] = ({"configured": bool(v), "hint": f"…{v[-4:]}" if len(v) >= 8 else ""} if secret else v)
        return out


_current: Settings | None = None


def init(db: Database, cipher: CredentialCipher) -> Settings:
    global _current
    _current = Settings(db, cipher)
    return _current


def get(name: str) -> str:
    if _current is None:  # pruebas o uso sin app: solo variables de entorno
        env, _ = FIELDS[name]
        return os.environ.get(env, "")
    return _current.get(name)
