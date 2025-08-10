"""Asynchronous SQLite convenience wrappers.

This module centralises database access for the Soundmap Discord bot. It
provides simple helper functions for common tasks such as executing queries,
fetching single or multiple rows and managing transactions. All functions
automatically initialise the database connection on first use and apply
migrations using the SQL file in the migrations directory.
"""

from __future__ import annotations

import logging
import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path

from .config import DATABASE_PATH

# Resolve the path from the environment variable and ensure its directory exists
DB_PATH = Path(DATABASE_PATH).expanduser()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Return a global aiosqlite connection. Initialise on first use.

    The connection uses Row objects, allowing dict-like access to columns.
    """
    global _db
    if _db is None:
        _db = await aiosqlite.connect(str(DB_PATH))
        _db.row_factory = aiosqlite.Row
    return _db


async def init_db() -> None:
    """Initialise the database schema by executing the migration file.

    This function reads the SQL commands from migrations/001_init.sql relative
    to the project root and executes them. It is idempotent and safe to run
    multiple times; tables will only be created if they do not already exist.
    """
    if DB_PATH.exists():
        size = DB_PATH.stat().st_size
        logging.info("Database path: %s (exists, %d bytes)", DB_PATH, size)
    else:
        logging.info("Database path: %s (missing)", DB_PATH)
    db = await get_db()
    # Resolve the path to the migration file relative to this file
    migration_path = Path(__file__).resolve().parent.parent / "migrations" / "001_init.sql"
    async with db.execute("PRAGMA foreign_keys = ON;"):
        pass  # ensure foreign keys enforced
    sql = migration_path.read_text(encoding="utf-8")
    # executescript automatically wraps statements in a single transaction
    await db.executescript(sql)
    await db.commit()
    # Ensure the new username column exists for the users table
    try:
        await db.execute("ALTER TABLE users ADD COLUMN username TEXT")
        await db.commit()
    except Exception:
        # Column already exists or cannot be added; ignore
        pass


async def fetch_one(query: str, params: tuple | list = ()) -> aiosqlite.Row | None:
    """Fetch a single row from the database.

    Returns None if no row matches the query.
    """
    db = await get_db()
    in_tx = db.in_transaction
    async with db.execute(query, params) as cursor:
        row = await cursor.fetchone()
    # ``aiosqlite`` implicitly opens a transaction for every statement. If we
    # weren't already in an explicit transaction we need to close this
    # autocommit transaction, otherwise subsequent ``BEGIN`` statements would
    # fail with "cannot start a transaction within a transaction".
    if not in_tx:
        await db.commit()
    return row


async def fetch_all(query: str, params: tuple | list = ()) -> list[aiosqlite.Row]:
    """Fetch all rows for the given query.

    Returns an empty list if no rows match.
    """
    db = await get_db()
    in_tx = db.in_transaction
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
    # See ``fetch_one`` for rationale. Commit only when we started the
    # transaction implicitly.
    if not in_tx:
        await db.commit()
    return rows


async def execute(query: str, params: tuple | list = ()) -> None:
    """Execute a query that does not return rows.

    The connection automatically commits the statement unless it is currently
    inside an explicit transaction started via :func:`transaction`. This allows
    callers to group multiple ``execute`` calls atomically without each one
    committing independently.
    """
    db = await get_db()
    in_tx = db.in_transaction
    await db.execute(query, params)
    # Commit immediately when not already inside an explicit transaction. This
    # mirrors the behaviour of autocommit mode and keeps ``transaction``
    # functional by deferring the final commit until exit.
    if not in_tx:
        await db.commit()


@asynccontextmanager
async def transaction():
    """Context manager for running a group of statements in a transaction.

    Usage:

        async with transaction():
            await execute(...)
            await execute(...)

    On successful exit, the transaction is committed. On exception, it is
    rolled back and the exception is re-raised.
    """
    db = await get_db()
    # Begin a transaction manually. aiosqlite autocommit is disabled inside the context.
    await db.execute("BEGIN")
    try:
        yield
    except Exception:
        await db.rollback()
        raise
    else:
        await db.commit()
