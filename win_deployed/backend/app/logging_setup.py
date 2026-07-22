"""Structured logging for the Phase 0 backend, built on structlog.

LOG_LEVEL   controls the level (default DEBUG).
LOG_FORMAT  `console` (default) → coloured, human-readable dev output;
            `json`              → one JSON object per line (for CloudWatch et al.).

structlog is wired through the stdlib logging backend, so:
  * existing `%s`-style call sites keep working unchanged
    (`log.debug("--> %s %s", method, path)`), and
  * third-party libraries that log via stdlib (httpx, botocore, …) flow through
    the same renderer.

Every request and every auth/proxy decision is logged so the SSO and AG-UI flows
stay traceable end to end.
"""

import logging
import os

import structlog

_CONFIGURED = False

# Processors shared by structlog-native loggers and foreign (stdlib) records, so
# both render identically. Order matters: add metadata, apply positional args,
# stamp time, then render exceptions.
_SHARED_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = os.environ.get("LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_name, logging.DEBUG)
    json_logs = os.environ.get("LOG_FORMAT", "console").strip().lower() == "json"

    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            # Hand off to the stdlib formatter below for final rendering.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer()
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Our own app loggers at the configured level; third-party libraries a notch
    # quieter so the trace stays readable.
    #
    # `aiosqlite` is the one that actually matters at DEBUG. It logs a line for
    # both the start AND the completion of every cursor, execute, fetchall,
    # close, commit and rollback — so a single `GET /api/agents` buries its own
    # `<-- GET /api/agents 200` under roughly forty lines of
    # `functools.partial(<built-in method cursor of sqlite3.Connection …>)`, with
    # the full SELECT column list repeated in each one. The trace this module
    # exists to keep readable was unreadable in practice; the proxy's
    # `-> AgentCore (SigV4)` line is the thing you are usually looking for and it
    # scrolls past in the flood.
    logging.getLogger("app").setLevel(level)
    for noisy in (
        "httpx",
        "httpcore",
        "botocore",
        "urllib3",
        "boto3",
        "aiosqlite",
        "asyncio",
    ):
        logging.getLogger(noisy).setLevel(logging.INFO)
    # NOT `sqlalchemy.engine`. Setting that logger to INFO is SQLAlchemy's
    # documented equivalent of `echo=True` — it TURNS ON full SQL echo rather
    # than quieting anything, which is the opposite of what this loop is for.
    # Left alone, SQLAlchemy keeps it at WARN and says nothing. Verified by
    # adding it here and watching every statement appear.

    _CONFIGURED = True
    structlog.stdlib.get_logger("app").info(
        "logging configured", level=level_name, format="json" if json_logs else "console"
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(f"app.{name}")
