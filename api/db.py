import os
import sqlite3
from contextlib import contextmanager
from typing import Any

USE_PG = bool(os.getenv("DATABASE_URL"))

if USE_PG:
    import psycopg2
    from psycopg2.extras import RealDictCursor


def _sqlite_path() -> str:
    path = os.getenv("SQLITE_PATH", "data/vault.db")
    try:
        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        return path
    except (OSError, PermissionError):
        tmp_dir = "/tmp/text-vault"
        os.makedirs(tmp_dir, exist_ok=True)
        return os.path.join(tmp_dir, "vault.db")


def init_db() -> None:
    if USE_PG:
        _init_postgres()
    else:
        _init_sqlite()


def _init_sqlite() -> None:
    with get_db() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                parent_folder_id INTEGER,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_folder_id) REFERENCES folders(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_folders_user ON folders(user_id);
            CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_folder_id);
            CREATE INDEX IF NOT EXISTS idx_files_user ON files(user_id);
            CREATE INDEX IF NOT EXISTS idx_files_folder ON files(folder_id);
            """
        )


def _init_postgres() -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS folders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                parent_folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS files (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_folders_user ON folders(user_id);
            CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_folder_id);
            CREATE INDEX IF NOT EXISTS idx_files_user ON files(user_id);
            CREATE INDEX IF NOT EXISTS idx_files_folder ON files(folder_id);
            """
        )


@contextmanager
def get_db():
    if USE_PG:
        conn = psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=RealDictCursor)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(_sqlite_path())
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def q(sql: str) -> str:
    return sql.replace("?", "%s") if USE_PG else sql


def row_to_dict(row: Any) -> dict:
    if row is None:
        return {}
    return dict(row)


def fetchone(conn, sql: str, params=()) -> dict | None:
    if USE_PG:
        cur = conn.cursor()
        cur.execute(q(sql), params)
        row = cur.fetchone()
        return dict(row) if row else None
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def fetchall(conn, sql: str, params=()) -> list[dict]:
    if USE_PG:
        cur = conn.cursor()
        cur.execute(q(sql), params)
        return [dict(r) for r in cur.fetchall()]
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def execute(conn, sql: str, params=()) -> int | None:
    if USE_PG:
        cur = conn.cursor()
        pg_sql = q(sql)
        if pg_sql.strip().upper().startswith("INSERT") and "RETURNING" not in pg_sql.upper():
            pg_sql = pg_sql.rstrip().rstrip(";") + " RETURNING id"
        cur.execute(pg_sql, params)
        if "RETURNING" in pg_sql.upper():
            row = cur.fetchone()
            return row["id"] if row else None
        return cur.rowcount
    cur = conn.execute(sql, params)
    return cur.lastrowid
