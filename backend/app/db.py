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
