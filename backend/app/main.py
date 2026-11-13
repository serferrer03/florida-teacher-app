"""API FastAPI de Florida Teacher App (Fase 1: login Microsoft + listado de cursos).

Privacidad desde el diseño (art. 25 RGPD): todo se queda en el PC, cifrado;
la tablet solo accede con el código de emparejamiento; nada se envía a terceros
salvo a Florida Oberta/Microsoft, que es donde ya están tus datos.
"""
from __future__ import annotations

import hmac
import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import BACKEND_DIR, get_settings
from .crypto import CredentialCipher
from .db import Database, now_iso
from .login_jobs import LoginJob, LoginJobs
from .moodle.client import (
    Credentials,
    MoodleAuthRequired,
    MoodleBusy,
    MoodleClient,
    MoodleError,
    MoodleLoginError,
)
from .session_store import SessionStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

settings = get_settings()
db = Database(settings.db_path)
cipher = CredentialCipher(settings.key_path)
store = SessionStore(settings.session_path, cipher, settings.session_max_days)
jobs = LoginJobs()
_moodle: MoodleClient | None = None


def get_moodle() -> MoodleClient:
    global _moodle
    if _moodle is None:
        try:
            _moodle = MoodleClient(settings, store)
        except MoodleError as exc:
            raise HTTPException(503, str(exc)) from exc
    return _moodle


# --------------------------------------------------------------- acceso LAN
MAX_FAILS, LOCK_SECONDS = 5, 300
_fails: dict[str, list[float]] = defaultdict(list)


def require_token(request: Request, x_app_token: str | None = Header(default=None)) -> None:
    """Toda la API exige el código de emparejamiento (cabecera X-App-Token)."""
    ip = request.client.host if request.client else "?"
    now = time.time()
    recent = [t for t in _fails[ip] if now - t < LOCK_SECONDS]
    _fails[ip] = recent
    if len(recent) >= MAX_FAILS:
        raise HTTPException(429, "Demasiados intentos con un código incorrecto. Espera 5 minutos.")
    if not x_app_token:
        raise HTTPException(401, "Falta el código de acceso")  # tablet sin vincular: no penaliza
    if not hmac.compare_digest(x_app_token.encode(), settings.access_token.encode()):
        recent.append(now)
        log.warning("Código de acceso incorrecto desde %s", ip)
        raise HTTPException(401, "Código de acceso incorrecto")
    _fails.pop(ip, None)


# -------------------------------------------------------------- utilidades
def stored_credentials() -> Credentials | None:
    row = db.get_credentials()
    if row is None:
        return None
    password = None
    if row["password_enc"] is not None:
        try:
            password = cipher.decrypt(row["password_enc"])
        except ValueError:
            password = None
    return Credentials(row["username"], password)


def moodle_http_error(exc: MoodleError) -> HTTPException:
    if isinstance(exc, MoodleAuthRequired):
        return HTTPException(409, str(exc))
    if isinstance(exc, MoodleBusy):
        return HTTPException(423, str(exc))
    if isinstance(exc, MoodleLoginError):
        return HTTPException(401, f"Inicio de sesión rechazado: {exc}")
    return HTTPException(502, str(exc))


def error_message(exc: Exception) -> str:
    if isinstance(exc, MoodleLoginError):
        return f"Inicio de sesión rechazado: {exc}"
    if isinstance(exc, TimeoutError):
        return "Se agotó el tiempo de espera"
    if isinstance(exc, MoodleError):
        return str(exc)
    log.exception("Error inesperado en el login")
    return "Error inesperado durante el inicio de sesión"


def wipe_everything() -> None:
    jobs.cancel()
    db.wipe()
    store.clear()
    settings.legacy_storage_state_path.unlink(missing_ok=True)
    cipher.reset()  # borrado criptográfico: lo cifrado antes ya no se puede leer


def lan_ip() -> str:
    """IP del PC en la red local (sin enviar nada: UDP connect no transmite paquetes)."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.1.1", 9))
            return s.getsockname()[0]
    except OSError:
        return "IP-DEL-PC"


# ------------------------------------------------------------------- app
@asynccontextmanager
async def lifespan(_: FastAPI):
    # Versiones anteriores guardaban las cookies sin cifrar: se eliminan.
    if settings.legacy_storage_state_path.exists():
        settings.legacy_storage_state_path.unlink()
        log.info("Eliminado estado de sesión antiguo sin cifrar")
    origin = "APP_ACCESS_TOKEN (.env)" if not settings.access_token_generated else "data/access_code"
    port = os.environ.get("PORT", "8000")
    print(
        "\n================================================================\n"
        f"  En la tablet abre:  http://{lan_ip()}:{port}\n"
        f"  Código de acceso para la tablet: {settings.access_token}\n"
        f"  (guardado en {origin}; no lo compartas)\n"
        "================================================================\n",
        flush=True,
    )
    yield


app = FastAPI(title="Florida Teacher App", version="0.2.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


auth = [Depends(require_token)]


class LoginIn(BaseModel):
    username: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=500)
    remember_password: bool = False
    manual: bool = False


class CodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=12, pattern=r"^[0-9A-Za-z]+$")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/status", dependencies=auth)
def status() -> dict:
    creds = db.get_credentials()
    return {
        "moodle_base_url": settings.moodle_base_url or None,
        "login_mode": settings.login_mode,
        "has_account": creds is not None,
        "username": creds["username"] if creds else None,
        "password_remembered": bool(creds and creds["password_enc"] is not None),
        "has_session": store.exists(),
        "last_login_ok": db.get_meta("last_login_ok"),
        "courses_synced_at": db.get_meta("courses_synced_at"),
        "login": jobs.current.to_dict() if jobs.current else None,
    }


# ------------------------------------------------------------------ login
@app.post("/api/login/start", dependencies=auth)
async def login_start(body: LoginIn) -> dict:
    if jobs.running():
        raise HTTPException(423, "Ya hay un inicio de sesión en curso")
    moodle = get_moodle()
    previous = stored_credentials()
    username = (body.username or (previous.username if previous else "")).strip()
    if not username and not body.manual:
        raise HTTPException(400, "Indica tu usuario (correo institucional)")
    password = body.password or (previous.password if previous and username == previous.username else None)
    creds = Credentials(username, password) if username else None
    # Si cambia la cuenta, no reutilizamos cookies de la anterior.
    fresh = previous is None or previous.username != username

    async def work(job: LoginJob) -> dict:
        info = await moodle.interactive_login(creds, job, manual=body.manual, fresh=fresh)
        if username:
            keep = password if body.remember_password else None
            db.save_credentials(username, cipher.encrypt(keep) if keep else None)
        db.set_meta("last_login_ok", now_iso())
        job.message = "Sesión iniciada. Descargando cursos…"
        try:
            courses = await moodle.list_courses(creds)
            db.replace_courses(courses)
            if not courses:
                info["courses_error"] = "Florida Oberta no devolvió ningún curso"
        except MoodleError as exc:
            info["courses_error"] = str(exc)
            log.warning("Login correcto pero falló la descarga de cursos: %s", exc)
        return info

    return jobs.start(work, error_message).to_dict()


@app.get("/api/login/status", dependencies=auth)
def login_status() -> dict:
    return jobs.current.to_dict() if jobs.current else {"state": "idle"}


@app.post("/api/login/code", dependencies=auth)
def login_code(body: CodeIn) -> dict:
    job = jobs.current
    if not job or job.state != "mfa_code":
        raise HTTPException(409, "No se está esperando ningún código")
    job.submit_code(body.code)
    job.state, job.message = "working", "Comprobando el código…"
    return job.to_dict()


@app.post("/api/login/cancel", dependencies=auth)
def login_cancel() -> dict:
    return {"cancelled": jobs.cancel()}


@app.post("/api/logout", dependencies=auth)
def logout() -> dict:
    """Cierra la sesión: borra cookies y contraseña recordada; mantiene usuario y cursos."""
    jobs.cancel()
    store.clear()
    creds = db.get_credentials()
    if creds:
        db.save_credentials(creds["username"], None)
    return {"ok": True}


# ----------------------------------------------------------------- cursos
@app.get("/api/courses", dependencies=auth)
def list_courses() -> dict:
    return {"courses": db.list_courses(), "synced_at": db.get_meta("courses_synced_at")}


@app.post("/api/courses/sync", dependencies=auth)
async def sync_courses() -> dict:
    try:
        courses = await get_moodle().list_courses(stored_credentials())
    except MoodleError as exc:
        raise moodle_http_error(exc) from exc
    db.replace_courses(courses)
    return {"courses": db.list_courses(), "synced_at": db.get_meta("courses_synced_at")}


# -------------------------------------------------------------- privacidad
@app.get("/api/privacy", dependencies=auth)
def privacy() -> dict:
    """Derecho de acceso: qué datos guarda la app en este PC."""
    creds = db.get_credentials()
    session_age = None
    if store.exists():
        mtime = datetime.fromtimestamp(settings.session_path.stat().st_mtime, timezone.utc)
        session_age = mtime.isoformat(timespec="seconds")
    return {
        "location": str(settings.data_dir),
        "items": [
            {"what": "Usuario de Florida Oberta", "stored": bool(creds), "detail": creds["username"] if creds else None,
             "protection": "Base de datos local"},
            {"what": "Contraseña", "stored": bool(creds and creds["password_enc"] is not None),
             "detail": "Solo si marcaste «Recordar contraseña»", "protection": "Cifrada (Fernet/AES)"},
            {"what": "Cookies de sesión (Moodle y Microsoft)", "stored": store.exists(),
             "detail": f"Guardada {session_age}; se borra sola a los {settings.session_max_days} días" if session_age else None,
             "protection": "Cifradas (Fernet/AES)"},
            {"what": "Lista de tus cursos", "stored": db.count_courses() > 0,
             "detail": f"{db.count_courses()} cursos (nombre, código, categoría, enlace)", "protection": "Base de datos local"},
        ],
        "not_stored": [
            "Datos de estudiantes (no se leen en esta fase)",
            "Códigos de verificación de Microsoft (se usan una vez y se descartan)",
            "Analítica, telemetría o envíos a terceros: no existen",
        ],
        "session_max_days": settings.session_max_days,
    }


@app.delete("/api/data", dependencies=auth)
def delete_all_data() -> dict:
    """Derecho de supresión: borra todo y destruye la clave de cifrado."""
    wipe_everything()
    return {"deleted": True}


# --- PWA compilada (frontend/dist) servida desde el mismo puerto -------------
DIST = Path(os.environ.get("FRONTEND_DIST") or BACKEND_DIR.parent / "frontend" / "dist")
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "Ruta de API no encontrada")
        target = (DIST / path).resolve()
        if path and target.is_file() and DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
