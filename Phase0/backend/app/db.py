"""Async database engine + session for the Phase 0 platform DB.

Defaults to a local SQLite file (`backend/phase0.db`). Set DATABASE_URL to
point at Postgres in a real deployment, e.g.
`postgresql+asyncpg://user:pass@host:5432/db` — nothing else changes about the
application, but the schema then belongs to Alembic rather than to `init_db`
below. See that function for why.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.logging_setup import get_logger
from app.models import Base

_DEFAULT_SQLITE = f"sqlite+aiosqlite:///{Path(__file__).resolve().parent.parent / 'phase0.db'}"
DATABASE_URL = os.environ.get("DATABASE_URL", _DEFAULT_SQLITE)

engine = create_async_engine(DATABASE_URL, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create the tables — for the local SQLite default ONLY.

    Zero-setup local dev is the whole point of the SQLite default: `uvicorn` and
    nothing else, no migration step. `create_all` keeps that.

    Anywhere else the schema belongs to Alembic, and running `create_all` there
    is actively harmful rather than merely redundant. `create_all` writes the
    tables but no `alembic_version` row, so a backend pod that reaches the
    database before the migration Job leaves Alembic looking at an unstamped
    database that already has every table — `alembic upgrade head` then fails on
    the first CREATE TABLE, and the deploy is wedged in a state no rerun clears.
    Multiple replicas racing each other into `create_all` is the same problem
    once per pod.

    So: run `alembic upgrade head` before starting the app on Postgres. On EKS
    that is the migration Job in `Phase0/deploy/k8s/`.
    """
    log = get_logger("db")
    if engine.dialect.name != "sqlite":
        log.info(
            "schema managed by Alembic on %s — skipping create_all "
            "(run 'alembic upgrade head' before starting the app)",
            engine.dialect.name,
        )
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with SessionLocal() as session:
        yield session
