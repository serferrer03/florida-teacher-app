"""API FastAPI de Florida Teacher App (Fase 1: login + listado de cursos)."""
from __future__ import annotations

import hmac
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import BACKEND_DIR, get_settings
from .crypto import CredentialCipher
from .db import Database, now_iso
from .moodle.client import Credentials, MoodleClient, MoodleError, MoodleLoginError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()
db = Database(settings.db_path)
cipher = CredentialCipher(settings.key_path)
_moodle: MoodleClient | None = None


def get_moodle() -> MoodleClient:
    global _moodle
    if _moodle is None:
        try:
            _moodle = MoodleClient(settings)
        except MoodleError as exc:
            raise HTTPException(503, str(exc)) from exc
    return _moodle


def require_token(x_app_token: str | None = Header(default=None)) -> None:
    """Si APP_ACCESS_TOKEN está definido, la API exige la cabecera X-App-Token."""
    if settings.access_token and not hmac.compare_digest(x_app_token or "", settings.access_token):
        raise HTTPException(401, "Token de acceso incorrecto")


def stored_credentials() -> Credentials:
    row = db.get_credentials()
    if row is None:
        raise HTTPException(400, "Primero guarda tus credenciales de Florida Oberta")
    try:
        return Credentials(row["username"], cipher.decrypt(row["password_enc"]))
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc


def moodle_http_error(exc: MoodleError) -> HTTPException:
    if isinstance(exc, MoodleLoginError):
        return HTTPException(401, f"Login en Florida Oberta fallido: {exc}")
    return HTTPException(502, str(exc))


app = FastAPI(title="Florida Teacher App", version="0.1.0")
# La PWA se sirve desde el mismo origen en producción; en desarrollo Vite hace de proxy.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class CredentialsIn(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=500)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/status", dependencies=[Depends(require_token)])
def status() -> dict:
    row = db.get_credentials()
    return {
        "moodle_base_url": settings.moodle_base_url or None,
        "has_credentials": row is not None,
        "username": row["username"] if row else None,
        "last_login_ok": db.get_meta("last_login_ok"),
        "courses_synced_at": db.get_meta("courses_synced_at"),
        "token_required": bool(settings.access_token),
    }


@app.put("/api/credentials", dependencies=[Depends(require_token)])
async def save_credentials(body: CredentialsIn, verify: bool = True) -> dict:
    """Guarda las credenciales cifradas. Con verify=true prueba el login antes."""
    creds = Credentials(body.username.strip(), body.password)
    user = None
    if verify:
        try:
            info = await get_moodle().check_login(creds)
        except MoodleError as exc:
            raise moodle_http_error(exc) from exc
        user = info.get("user")
        db.set_meta("last_login_ok", now_iso())
    db.save_credentials(creds.username, cipher.encrypt(creds.password))
    return {"saved": True, "verified": verify, "user": user}


@app.delete("/api/credentials", dependencies=[Depends(require_token)])
def delete_credentials() -> dict:
    db.delete_credentials()
    settings.storage_state_path.unlink(missing_ok=True)
    return {"deleted": True}


@app.post("/api/login/test", dependencies=[Depends(require_token)])
async def test_login() -> dict:
    try:
        info = await get_moodle().check_login(stored_credentials())
    except MoodleError as exc:
        raise moodle_http_error(exc) from exc
    db.set_meta("last_login_ok", now_iso())
    return info


@app.get("/api/courses", dependencies=[Depends(require_token)])
def list_courses() -> dict:
    return {"courses": db.list_courses(), "synced_at": db.get_meta("courses_synced_at")}


@app.post("/api/courses/sync", dependencies=[Depends(require_token)])
async def sync_courses() -> dict:
    try:
        courses = await get_moodle().list_courses(stored_credentials())
    except MoodleError as exc:
        raise moodle_http_error(exc) from exc
    db.replace_courses(courses)
    return {"courses": db.list_courses(), "synced_at": db.get_meta("courses_synced_at")}


# --- PWA compilada (frontend/dist) servida desde el mismo puerto -------------
DIST = Path(BACKEND_DIR.parent / "frontend" / "dist")
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
