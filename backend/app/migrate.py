"""Lightweight SQLite migrations for schema evolution during M1+."""
from sqlalchemy import text

from .database import engine


def _columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": table},
    ).fetchone()
    return row is not None


def run_migrations() -> None:
    with engine.begin() as conn:
        # M1: add Exercise.youtube_url
        if _table_exists(conn, "exercises"):
            cols = _columns(conn, "exercises")
            if "youtube_url" not in cols:
                conn.execute(text("ALTER TABLE exercises ADD COLUMN youtube_url VARCHAR DEFAULT ''"))
