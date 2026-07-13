"""Async database engine + session for the Phase 0 platform DB.

Defaults to a local SQLite file (`Phase0/backend/phase0.db`). Set DATABASE_URL to
point at Postgres in a real deployment, e.g.
`postgresql+asyncpg://user:pass@host:5432/db` — nothing else changes.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base

_DEFAULT_SQLITE = f"sqlite+aiosqlite:///{Path(__file__).resolve().parent.parent / 'phase0.db'}"
DATABASE_URL = os.environ.get("DATABASE_URL", _DEFAULT_SQLITE)

engine = create_async_engine(DATABASE_URL, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create tables if they do not exist (Phase 0 has no migration tool yet)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with SessionLocal() as session:
        yield session
