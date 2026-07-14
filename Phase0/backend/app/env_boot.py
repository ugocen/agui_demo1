"""Environment loading, shared by every entry point.

Precedence: a component-local `backend/.env` wins over a repo-root `.env` one
level up, and real process env vars win over both (`override=False`). Both files
are optional, so the same code runs in the monorepo layout (repo-root .env) and
in a standalone backend checkout (only backend/.env).

This lives in its own module so that EVERY entry point resolves config
identically. `app/main.py` calls it before importing `app.*`; `alembic/env.py`
calls it before importing `app.db`. Without that, the Alembic CLI would never see
`backend/.env`, so `DATABASE_URL=postgresql+asyncpg://...` set there would be
ignored and migrations would silently target the local SQLite default while the
running app used Postgres.
"""

from pathlib import Path

from dotenv import load_dotenv

_APP_DIR = Path(__file__).resolve().parent


def load_env() -> None:
    """Load backend/.env then the repo-root .env, without overriding real env vars."""
    for env_file in (_APP_DIR.parent / ".env", _APP_DIR.parent.parent / ".env"):
        if env_file.exists():
            load_dotenv(env_file)
