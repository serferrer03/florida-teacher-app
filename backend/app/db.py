"""Persistencia SQLite mínima (sin ORM)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS credentials (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    username TEXT NOT NULL,
    password_enc BLOB,                -- NULL si no se recuerda la contraseña
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY,           -- id del curso en Moodle
    fullname TEXT NOT NULL,
    shortname TEXT,
    category TEXT,
    url TEXT NOT NULL,
    synced_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    cmid INTEGER NOT NULL,              -- id de la actividad en Moodle
    name TEXT NOT NULL,
    due TEXT,
    url TEXT NOT NULL,
    files INTEGER NOT NULL DEFAULT 0,
    restricted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    data TEXT NOT NULL,                 -- JSON del formulario con fechas relativas
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS autoeval (
    cmid INTEGER PRIMARY KEY,           -- tarea en Moodle
    course_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    criteria TEXT NOT NULL,             -- criterios / rúbrica del profesor (sin datos del alumnado)
    grade_max REAL NOT NULL,
    close_at TEXT NOT NULL,             -- cuándo evaluar (cierre de la tarea, hora local ISO)
    enabled INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL DEFAULT 'waiting',   -- waiting | running | review | done | error
    last_error TEXT,
    evaluated_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS autoeval_results (
    cmid INTEGER NOT NULL,
    userid INTEGER NOT NULL,
    name_enc BLOB NOT NULL,             -- nombre del alumno CIFRADO
    grade REAL,
    observation_enc BLOB,               -- observación CIFRADA
    status TEXT NOT NULL,               -- proposed | needs_review | published
    updated_at TEXT NOT NULL,
    PRIMARY KEY (cmid, userid)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        if not path.exists():
            path.touch(mode=0o600)  # solo el usuario del PC puede leer la BD
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        # v0.1: password_enc era NOT NULL; ahora es opcional.
        cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(credentials)")}
        if cols.get("password_enc") is not None and cols["password_enc"]["notnull"]:
            conn.executescript(
                "ALTER TABLE credentials RENAME TO credentials_old;"
                + SCHEMA.split(";")[0] + ";"
                "INSERT INTO credentials SELECT * FROM credentials_old;"
                "DROP TABLE credentials_old;"
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- credenciales -------------------------------------------------
    def save_credentials(self, username: str, password_enc: bytes | None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO credentials (id, username, password_enc, updated_at) VALUES (1, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET username=excluded.username, "
                "password_enc=excluded.password_enc, updated_at=excluded.updated_at",
                (username, password_enc, now_iso()),
            )

    def get_credentials(self) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM credentials WHERE id = 1").fetchone()

    def delete_credentials(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM credentials")

    # --- cursos -------------------------------------------------------
    def replace_courses(self, courses: list[dict]) -> None:
        ts = now_iso()
        with self.connect() as conn:
            conn.execute("DELETE FROM courses")
            conn.executemany(
                "INSERT INTO courses (id, fullname, shortname, category, url, synced_at) "
                "VALUES (:id, :fullname, :shortname, :category, :url, :synced_at)",
                [{**c, "synced_at": ts} for c in courses],
            )
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('courses_synced_at', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (ts,),
            )

    def list_courses(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM courses ORDER BY fullname COLLATE NOCASE").fetchall()
            return [dict(r) for r in rows]

    def add_assignment(self, course_id: int, cmid: int, name: str, due: str | None, url: str,
                       files: int, restricted: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO assignments (course_id, cmid, name, due, url, files, restricted, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (course_id, cmid, name, due, url, files, int(restricted), now_iso()),
            )

    def list_assignments(self, course_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM assignments WHERE course_id = ? ORDER BY id DESC", (course_id,)).fetchall()
            return [dict(r) for r in rows]

    def count_assignments(self) -> int:
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]

    def add_template(self, name: str, data: str) -> int:
        with self.connect() as conn:
            return conn.execute("INSERT INTO templates (name, data, created_at) VALUES (?, ?, ?)",
                                (name, data, now_iso())).lastrowid

    def list_templates(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM templates ORDER BY name COLLATE NOCASE").fetchall()
            return [dict(r) for r in rows]

    def delete_template(self, template_id: int) -> bool:
        with self.connect() as conn:
            return conn.execute("DELETE FROM templates WHERE id = ?", (template_id,)).rowcount > 0

    # --- evaluación automática -----------------------------------------
    def upsert_autoeval(self, cmid: int, course_id: int, name: str, criteria: str, grade_max: float,
                        close_at: str, enabled: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO autoeval (cmid, course_id, name, criteria, grade_max, close_at, enabled, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(cmid) DO UPDATE SET name=excluded.name, "
                "criteria=excluded.criteria, grade_max=excluded.grade_max, close_at=excluded.close_at, "
                "enabled=excluded.enabled, updated_at=excluded.updated_at",
                (cmid, course_id, name, criteria, grade_max, close_at, int(enabled), now_iso()))

    def get_autoeval(self, cmid: int) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM autoeval WHERE cmid = ?", (cmid,)).fetchone()
            return dict(row) if row else None

    def list_autoeval(self, course_id: int | None = None) -> list[dict]:
        with self.connect() as conn:
            if course_id is None:
                rows = conn.execute("SELECT * FROM autoeval").fetchall()
            else:
                rows = conn.execute("SELECT * FROM autoeval WHERE course_id = ?", (course_id,)).fetchall()
            return [dict(r) for r in rows]

    def set_autoeval_state(self, cmid: int, state: str, error: str | None = None,
                           evaluated: bool = False) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE autoeval SET state = ?, last_error = ?, updated_at = ?"
                + (", evaluated_at = ?" if evaluated else "") + " WHERE cmid = ?",
                (state, error, now_iso(), *([now_iso()] if evaluated else []), cmid))

    def delete_autoeval(self, cmid: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM autoeval WHERE cmid = ?", (cmid,))
            conn.execute("DELETE FROM autoeval_results WHERE cmid = ?", (cmid,))

    def save_result(self, cmid: int, userid: int, name_enc: bytes, grade: float | None,
                    observation_enc: bytes | None, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO autoeval_results (cmid, userid, name_enc, grade, observation_enc, status, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(cmid, userid) DO UPDATE SET name_enc=excluded.name_enc, "
                "grade=excluded.grade, observation_enc=excluded.observation_enc, status=excluded.status, "
                "updated_at=excluded.updated_at",
                (cmid, userid, name_enc, grade, observation_enc, status, now_iso()))

    def list_results(self, cmid: int) -> list[dict]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM autoeval_results WHERE cmid = ? ORDER BY userid", (cmid,)).fetchall()]

    def purge_results(self, published_before: str, any_before: str) -> int:
        """Minimización: borra las ya publicadas (tras 1 día) y cualquier propuesta de más de 30 días."""
        with self.connect() as conn:
            return conn.execute(
                "DELETE FROM autoeval_results WHERE (status = 'published' AND updated_at < ?) OR updated_at < ?",
                (published_before, any_before)).rowcount

    def count_results(self) -> int:
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM autoeval_results").fetchone()[0]

    def count_courses(self) -> int:
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]

    def wipe(self) -> None:
        """Borra todos los datos guardados (derecho de supresión)."""
        with self.connect() as conn:
            conn.execute("DELETE FROM credentials")
            conn.execute("DELETE FROM courses")
            conn.execute("DELETE FROM assignments")
            conn.execute("DELETE FROM templates")
            conn.execute("DELETE FROM autoeval")
            conn.execute("DELETE FROM autoeval_results")
            conn.execute("DELETE FROM meta")
        with self.connect() as conn:
            conn.execute("VACUUM")  # no dejar restos en páginas libres del archivo

    def get_meta(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
