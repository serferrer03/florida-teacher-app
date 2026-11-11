"""Configuración leída de variables de entorno (y de backend/.env si existe)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


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
    chromium_executable: str | None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def key_path(self) -> Path:
        return self.data_dir / "secret.key"

    @property
    def storage_state_path(self) -> Path:
        return self.data_dir / "storage_state.json"


@lru_cache
def get_settings() -> Settings:
    _load_dotenv(BACKEND_DIR / ".env")
    data_dir = Path(os.environ.get("APP_DATA_DIR") or BACKEND_DIR / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        data_dir.chmod(0o700)  # BD, clave y sesión: solo el usuario del PC
    except OSError:
        pass
    return Settings(
        moodle_base_url=os.environ.get("MOODLE_BASE_URL", "").rstrip("/"),
        headless=_bool(os.environ.get("MOODLE_HEADLESS"), True),
        timeout_ms=int(os.environ.get("MOODLE_TIMEOUT_MS") or 30000),
        data_dir=data_dir,
        access_token=os.environ.get("APP_ACCESS_TOKEN", "").strip(),
        chromium_executable=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None,
    )
