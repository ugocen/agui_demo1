"""Alembic environment — async, wired to the app's models and DATABASE_URL.

Uses the same URL resolution as `app/db.py` (DATABASE_URL env, else the local
SQLite default) so migrations and the running app always target the same DB.
`render_as_batch` is on so SQLite (which lacks full ALTER) can still apply
column changes in future migrations.

`load_env()` runs before `app.db` is imported — app/db.py reads DATABASE_URL at
import time, and only the app's own entry point would otherwise have loaded the
.env file. Without this, `alembic upgrade head` would ignore a DATABASE_URL set
in backend/.env and silently migrate the local SQLite file instead of Postgres.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.env_boot import load_env

load_env()

from app.db import DATABASE_URL  # noqa: E402 — must follow load_env()
from app.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(DATABASE_URL)
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
