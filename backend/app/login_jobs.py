"""Inicio de sesión interactivo en segundo plano, consultado por la tablet.

La tablet arranca el login y va preguntando el estado. Cuando Microsoft pide
MFA, el estado lo indica (número a escribir en Authenticator, aprobación push
o código) y la tablet lo muestra; el código se entrega con submit_code().
"""
from __future__ import annotations

import asyncio
import secrets
import time
from typing import Awaitable, Callable

FINAL_STATES = {"success", "error", "cancelled"}


class LoginJob:
    def __init__(self) -> None:
        self.id = secrets.token_urlsafe(8)
        self.state = "working"
        self.message = "Conectando con Florida Oberta…"
        self.number: str | None = None
        self.result: dict | None = None
        self.started = time.time()
        self._codes: asyncio.Queue[str] = asyncio.Queue()
        self.task: asyncio.Task | None = None

    # --- LoginUI ------------------------------------------------------
    async def update(self, state: str, **info: object) -> None:
        if state == "done":
            return  # el estado final lo fija el gestor cuando termina todo
        self.state = state
        self.number = str(info["number"]) if info.get("number") else None
        if state == "manual":
            self.message = "Inicia sesión en la ventana de Chromium que se ha abierto en el PC"
        elif info.get("message"):
            self.message = str(info["message"])

    async def request_code(self) -> str:
        self.state = "mfa_code"
        self.number = None
        self.message = "Introduce el código de verificación que te ha enviado Microsoft"
        return await self._codes.get()

    def submit_code(self, code: str) -> None:
        self._codes.put_nowait(code)

    # --- gestión ------------------------------------------------------
    @property
    def finished(self) -> bool:
        return self.state in FINAL_STATES

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "state": self.state,
            "message": self.message,
            "number": self.number,
            "result": self.result,
        }


class LoginJobs:
    def __init__(self) -> None:
        self.current: LoginJob | None = None

    def running(self) -> bool:
        return self.current is not None and not self.current.finished

    def start(self, work: Callable[[LoginJob], Awaitable[dict]], on_error: Callable[[Exception], str]) -> LoginJob:
        job = LoginJob()
        self.current = job

        async def runner() -> None:
            try:
                job.result = await work(job)
                job.state, job.message, job.number = "success", "Sesión iniciada", None
            except asyncio.CancelledError:
                job.state, job.message, job.number = "cancelled", "Inicio de sesión cancelado", None
            except Exception as exc:  # noqa: BLE001 - se muestra en la tablet
                job.state, job.message, job.number = "error", on_error(exc), None

        job.task = asyncio.create_task(runner())
        return job

    def cancel(self) -> bool:
        if self.running() and self.current.task:
            self.current.task.cancel()
            return True
        return False
