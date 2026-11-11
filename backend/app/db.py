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
    password_enc BLOB NOT NULL,
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
        with self.connect() as conn:
            conn.executescript(SCHEMA)

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
    def save_credentials(self, username: str, password_enc: bytes) -> None:
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
