"""Configuración leída de variables de entorno (y de backend/.env si existe)."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MOODLE_URL = "https://www.floridaoberta.com"


def _load_dotenv(path: Path) -> None:
    """Carga KEY=VALUE simples sin dependencias; no pisa variables ya definidas."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


@dataclass(frozen=True)
class Settings:
    moodle_base_url: str
    headless: bool
    timeout_ms: int
    data_dir: Path
    access_token: str
    access_token_generated: bool
    chromium_executable: str | None
    login_mode: str            # auto | microsoft | moodle
    login_timeout_s: int       # tiempo máximo para completar el login (incluida la MFA)
    ms_stay_signed_in: bool    # responder "Sí" a "¿Mantener la sesión iniciada?"
    session_max_days: int      # caducidad local de la sesión cifrada

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def key_path(self) -> Path:
        return self.data_dir / "secret.key"

    @property
    def session_path(self) -> Path:
        return self.data_dir / "session.enc"

    @property
    def legacy_storage_state_path(self) -> Path:
        # Fase 1 inicial guardaba las cookies sin cifrar: se borra al arrancar.
        return self.data_dir / "storage_state.json"


def _access_token(data_dir: Path) -> tuple[str, bool]:
    """Código que la tablet debe enviar. Si no se define, se genera uno y se guarda."""
    env = os.environ.get("APP_ACCESS_TOKEN", "").strip()
    if env:
        return env, False
    path = data_dir / "access_code"
    if path.exists():
        return path.read_text(encoding="utf-8").strip(), True
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I
    code = "".join(secrets.choice(alphabet) for _ in range(10))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(code)
    return code, True


@lru_cache
def get_settings() -> Settings:
    _load_dotenv(BACKEND_DIR / ".env")
    data_dir = Path(os.environ.get("APP_DATA_DIR") or BACKEND_DIR / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        data_dir.chmod(0o700)  # BD, clave y sesión: solo el usuario del PC
    except OSError:
        pass
    token, generated = _access_token(data_dir)
    mode = (os.environ.get("LOGIN_MODE") or "auto").strip().lower()
    return Settings(
        moodle_base_url=(os.environ.get("MOODLE_BASE_URL") or DEFAULT_MOODLE_URL).rstrip("/"),
        headless=_bool(os.environ.get("MOODLE_HEADLESS"), True),
        timeout_ms=int(os.environ.get("MOODLE_TIMEOUT_MS") or 30000),
        data_dir=data_dir,
        access_token=token,
        access_token_generated=generated,
        chromium_executable=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None,
        login_mode=mode if mode in {"auto", "microsoft", "moodle"} else "auto",
        login_timeout_s=int(os.environ.get("LOGIN_TIMEOUT_S") or 180),
        ms_stay_signed_in=_bool(os.environ.get("MS_STAY_SIGNED_IN"), True),
        session_max_days=int(os.environ.get("SESSION_MAX_DAYS") or 14),
    )
