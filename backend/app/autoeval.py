"""Evaluación automática al cerrarse una tarea.

Flujo: el profesor activa la evaluación de una tarea (criterios, nota máxima,
fecha de cierre). Un programador revisa cada 5 minutos; al pasar la fecha de
cierre descarga las entregas, pide a Claude una nota y una observación para cada
una y actualiza la hoja de Google. Las notas quedan como PROPUESTAS: solo se
publican en Florida Oberta cuando el profesor las revisa y confirma.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from . import ai_eval, sheets
from .crypto import CredentialCipher
from .db import Database
from .moodle.client import Credentials, MoodleAuthRequired, MoodleClient, MoodleError

log = logging.getLogger(__name__)
CHECK_EVERY_S = 300
Evaluator = Callable[[str, str, float, ai_eval.Submission], Awaitable[ai_eval.Evaluation]]

STATUS_LABEL = {"proposed": "Propuesta IA (pendiente de revisar)",
                "needs_review": "Requiere revisión manual",
                "published": "Publicada en Florida Oberta"}


class AutoEvaluator:
    def __init__(self, db: Database, cipher: CredentialCipher, get_moodle: Callable[[], MoodleClient],
                 get_creds: Callable[[], Credentials | None], evaluator: Evaluator = ai_eval.evaluate) -> None:
        self.db, self.cipher = db, cipher
        self.get_moodle, self.get_creds = get_moodle, get_creds
        self.evaluator = evaluator
        self._task: asyncio.Task | None = None
        self._running: set[int] = set()

    # ------------------------------------------------------------ programador
    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_due()
            except Exception:  # noqa: BLE001 - el programador nunca debe morir
                log.exception("Error en el programador de evaluación automática")
            await asyncio.sleep(CHECK_EVERY_S)

    async def run_due(self) -> None:
        now = datetime.now(timezone.utc)
        self.db.purge_results((now - timedelta(days=1)).isoformat(timespec="seconds"),
                              (now - timedelta(days=30)).isoformat(timespec="seconds"))
        if not ai_eval.configured():
            return
        local_now = datetime.now().strftime("%Y-%m-%dT%H:%M")
        for a in self.db.list_autoeval():
            if a["enabled"] and a["state"] == "waiting" and a["close_at"] <= local_now:
                await self.run(a["cmid"])

    # ------------------------------------------------------------- evaluación
    async def run(self, cmid: int) -> None:
        a = self.db.get_autoeval(cmid)
        if not a or cmid in self._running:
            return
        self._running.add(cmid)
        self.db.set_autoeval_state(cmid, "running")
        try:
            subs = await self.get_moodle().collect_submissions(self.get_creds(), cmid)
            log.info("Evaluación automática: %d entregas", len(subs))
            rows = []
            for s in subs:
                ev = await self.evaluator(a["name"], a["criteria"], a["grade_max"],
                                          ai_eval.Submission(s["onlinetext"], s["files"]))
                obs = ev.observation if not ev.needs_review else (
                    f"[Revisar: {ev.review_reason}] {ev.observation}".strip())
                status = "needs_review" if ev.needs_review else "proposed"
                self.db.save_result(cmid, s["userid"], self.cipher.encrypt(s["name"]), ev.grade,
                                    self.cipher.encrypt(obs), status)
                rows.append(self.sheet_row(a, s["name"], ev.grade, obs, status))
            err = await sheets.push(rows)
            self.db.set_autoeval_state(cmid, "review", err, evaluated=True)
        except MoodleAuthRequired:
            # se reintentará en la siguiente vuelta cuando se reconecte la sesión
            self.db.set_autoeval_state(cmid, "waiting", "Hace falta reconectar con Florida Oberta")
        except MoodleError as exc:
            self.db.set_autoeval_state(cmid, "error", str(exc))
        except Exception as exc:  # noqa: BLE001 - p. ej. error de la API de IA
            log.warning("Evaluación automática fallida (%s)", type(exc).__name__)
            self.db.set_autoeval_state(cmid, "error", f"{type(exc).__name__}: {str(exc)[:300]}")
        finally:
            self._running.discard(cmid)

    def sheet_row(self, a: dict, name: str, grade: float | None, obs: str, status: str) -> dict:
        course = next((c["fullname"] for c in self.db.list_courses() if c["id"] == a["course_id"]), str(a["course_id"]))
        return {"curso": course, "tarea": a["name"], "alumno": name,
                "nota": "" if grade is None else grade, "observacion": obs, "estado": STATUS_LABEL[status]}

    def results(self, cmid: int) -> list[dict]:
        out = []
        for r in self.db.list_results(cmid):
            out.append({"userid": r["userid"], "name": self.cipher.decrypt(r["name_enc"]), "grade": r["grade"],
                        "observation": self.cipher.decrypt(r["observation_enc"]) if r["observation_enc"] else "",
                        "status": r["status"]})
        return sorted(out, key=lambda r: r["name"].lower())
