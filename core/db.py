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
    # Schema is defined fully in the migration; no additional columns needed here.


async def fetch_one(query: str, params: tuple | list = ()) -> aiosqlite.Row | None:
    """Fetch a single row from the database.

    Returns None if no row matches the query.
    """
    db = await get_db()
    async with db.execute(query, params) as cursor:
        row = await cursor.fetchone()
    # End the implicit transaction started by the SELECT unless we're inside an
    # explicit transaction managed by :func:`transaction`.
    if not db.in_transaction:
        await db.commit()
    return row


async def fetch_all(query: str, params: tuple | list = ()) -> list[aiosqlite.Row]:
    """Fetch all rows for the given query.

    Returns an empty list if no rows match.
    """
    db = await get_db()
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
    # Like ``fetch_one``, ensure we leave autocommit mode if the SELECT started
    # an implicit transaction.
    if not db.in_transaction:
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
    await db.execute(query, params)
    # Only commit if we're not already inside an explicit transaction. This
    # keeps ``transaction`` functional by deferring the commit until the context
    # manager completes.
    if not db.in_transaction:
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
