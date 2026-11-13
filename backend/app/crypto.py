"""Cifrado local con Fernet (AES-128-CBC + HMAC-SHA256).

La clave se genera la primera vez y se guarda en data/secret.key con permisos 600.
Se usa para la contraseña (si eliges recordarla) y para las cookies de sesión.
Quien tenga acceso a ese archivo puede descifrar: protege tu usuario del PC y
activa el cifrado de disco (BitLocker / FileVault / LUKS).
"""
from __future__ import annotations

import hashlib
import logging
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


log = logging.getLogger(__name__)
KEYRING_SERVICE = "florida-teacher-app"


def _system_keyring():
    """Llavero del sistema (Administrador de credenciales de Windows, Llavero de macOS,
    Secret Service en Linux) o None si no hay ninguno utilizable."""
    try:
        import keyring
        from keyring.backends import fail
    except ImportError:
        return None
    kr = keyring.get_keyring()
    if isinstance(kr, fail.Keyring) or getattr(kr, "priority", 0) < 1:
        return None
    return kr


class CredentialCipher:
    def __init__(self, key_path: Path, use_keyring: bool = False) -> None:
        self._key_path = key_path
        self._kr = _system_keyring() if use_keyring else None
        # una entrada por carpeta de datos (varias instalaciones no se pisan)
        self._account = "clave-" + hashlib.sha256(str(key_path.parent.resolve()).encode()).hexdigest()[:16]
        self._fernet = Fernet(self._load_or_create_key())

    @property
    def storage(self) -> str:
        return "Llavero del sistema" if self._kr else f"Archivo {self._key_path.name} (permisos 600)"

    def _load_or_create_key(self) -> bytes:
        if self._kr is not None:
            try:
                stored = self._kr.get_password(KEYRING_SERVICE, self._account)
                if stored:
                    self._key_path.unlink(missing_ok=True)
                    return stored.encode()
                key = (self._key_path.read_bytes().strip() if self._key_path.exists()
                       else Fernet.generate_key())
                self._kr.set_password(KEYRING_SERVICE, self._account, key.decode())
                if self._kr.get_password(KEYRING_SERVICE, self._account) == key.decode():
                    self._key_path.unlink(missing_ok=True)  # migrada al llavero
                    log.info("Clave de cifrado guardada en el llavero del sistema")
                    return key
            except Exception:  # noqa: BLE001 - cualquier fallo del llavero -> archivo
                log.warning("Llavero del sistema no disponible: la clave se guarda en archivo")
            self._kr = None
        if self._key_path.exists():
            return self._key_path.read_bytes().strip()
        key = Fernet.generate_key()
        write_private(self._key_path, key)
        return key

    def reset(self) -> None:
        """Destruye la clave y crea otra: lo cifrado antes queda irrecuperable."""
        if self._kr is not None:
            try:
                self._kr.delete_password(KEYRING_SERVICE, self._account)
            except Exception:  # noqa: BLE001
                pass
        self._key_path.unlink(missing_ok=True)
        self._fernet = Fernet(self._load_or_create_key())

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, token: bytes) -> str:
        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except InvalidToken as exc:  # clave cambiada o datos corruptos
            raise ValueError("No se pudieron descifrar los datos guardados") from exc
