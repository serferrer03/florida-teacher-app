"""Cifrado local con Fernet (AES-128-CBC + HMAC-SHA256).

La clave se genera la primera vez y se guarda en data/secret.key con permisos 600.
Se usa para la contraseña (si eliges recordarla) y para las cookies de sesión.
Quien tenga acceso a ese archivo puede descifrar: protege tu usuario del PC y
activa el cifrado de disco (BitLocker / FileVault / LUKS).
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def write_private(path: Path, data: bytes) -> None:
    """Escribe un archivo legible solo por el usuario actual (600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


class CredentialCipher:
    def __init__(self, key_path: Path) -> None:
        self._key_path = key_path
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        if self._key_path.exists():
            return self._key_path.read_bytes().strip()
        key = Fernet.generate_key()
        write_private(self._key_path, key)
        return key

    def reset(self) -> None:
        """Destruye la clave y crea otra: lo cifrado antes queda irrecuperable."""
        self._key_path.unlink(missing_ok=True)
        self._fernet = Fernet(self._load_or_create_key())

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, token: bytes) -> str:
        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except InvalidToken as exc:  # clave cambiada o datos corruptos
            raise ValueError("No se pudieron descifrar los datos guardados") from exc
