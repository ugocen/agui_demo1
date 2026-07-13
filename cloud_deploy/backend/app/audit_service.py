"""Audit-trail persistence.

A thin helper over the `audit_log` table. Records intentional platform mutations
(admin catalog edits, syncs) with the acting Entra ID identity. Operational logs
belong in structlog → stdout, not here — this table is for the "who changed what,
when?" question and is meant to stay low-volume.
"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_setup import get_logger
from app.models import AuditLog

log = get_logger("audit")


async def record_audit(
    db: AsyncSession,
    *,
    actor: dict | None,
    action: str,
    target: str = "",
    detail: object = None,
) -> AuditLog:
    """Append one audit row and commit.

    `actor` is the user dict from `require_user`/`require_roles` (may be the
    anonymous dict in iam mode, where oid/email are None). `detail` is JSON-encoded
    (str values are stored as-is).
    """
    actor = actor or {}
    if detail is None:
        detail_str = ""
    elif isinstance(detail, str):
        detail_str = detail
    else:
        detail_str = json.dumps(detail, default=str, ensure_ascii=False)

    entry = AuditLog(
        actor_oid=actor.get("oid") or "",
        actor_email=actor.get("email") or "",
        action=action,
        target=target,
        detail=detail_str,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    log.info(
        "audit recorded",
        action=action,
        target=target,
        actor_email=entry.actor_email or None,
    )
    return entry


async def list_audit(db: AsyncSession, *, limit: int = 200) -> list[AuditLog]:
    """Most-recent audit rows first (newest at the top)."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
    return list((await db.scalars(stmt)).all())
