"""Estado de sesión del navegador (cookies de Moodle y Microsoft) cifrado en disco.

Las cookies de sesión dan acceso a tu cuenta institucional, así que nunca se
guardan en claro y caducan tras SESSION_MAX_DAYS días.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .crypto import CredentialCipher, write_private

log = logging.getLogger(__name__)


class SessionStore:
    def __init__(self, path: Path, cipher: CredentialCipher, max_days: int) -> None:
        self.path = path
        self.cipher = cipher
        self.max_age = max_days * 86400

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        if time.time() - self.path.stat().st_mtime > self.max_age:
            log.info("Sesión guardada caducada por antigüedad: se elimina")
            self.clear()
            return None
        try:
            return json.loads(self.cipher.decrypt(self.path.read_bytes()))
        except (ValueError, json.JSONDecodeError):
            self.clear()
            return None

    def save(self, state: dict) -> None:
        write_private(self.path, self.cipher.encrypt(json.dumps(state)))

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)

    def exists(self) -> bool:
        return self.path.exists()
