"""Agent-catalog persistence + AgentCore sync.

The catalog is the platform's own registry of agents and the single source the
proxy routes on. AgentCore is the source of truth for what is *deployed* (ARN,
protocol, status, version); the catalog adds what AgentCore does not know
(display name, description, ui_mode, enabled) and is where the admin screen edits
live. The two are joined by `runtime_arn`. Nothing about agents lives in env —
the catalog is populated purely by `sync_from_agentcore` (see agents_catalog.py).
"""

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EDITABLE_FIELDS, UI_MODES, AgentCatalogEntry


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "agent"


async def list_entries(db: AsyncSession, *, enabled_only: bool = False) -> list[AgentCatalogEntry]:
    stmt = select(AgentCatalogEntry).order_by(AgentCatalogEntry.agent_id)
    if enabled_only:
        stmt = stmt.where(AgentCatalogEntry.enabled.is_(True))
    return list((await db.scalars(stmt)).all())


async def get_by_agent_id(db: AsyncSession, agent_id: str) -> AgentCatalogEntry | None:
    return await db.scalar(select(AgentCatalogEntry).where(AgentCatalogEntry.agent_id == agent_id))


async def get_by_arn(db: AsyncSession, arn: str) -> AgentCatalogEntry | None:
    return await db.scalar(select(AgentCatalogEntry).where(AgentCatalogEntry.runtime_arn == arn))


async def _unique_agent_id(db: AsyncSession, base: str) -> str:
    candidate, n = base, 2
    while await get_by_agent_id(db, candidate):
        candidate, n = f"{base}-{n}", n + 1
    return candidate


async def sync_from_agentcore(db: AsyncSession, runtimes: list[dict]) -> dict:
    """Upsert the catalog from live AgentCore discovery — the only way agents
    enter the catalog (there is no env/seed path).

    New **AG-UI** runtimes are auto-registered with `ui_mode='a2ui'` (the default
    for freshly discovered agents); an admin can switch one to `static` in the
    admin screen to get the hand-authored cards, and that choice persists.
    Existing entries only get their AgentCore-sourced (read-only) fields refreshed
    here — editable platform fields (display_name, description, ui_mode, enabled,
    required_role) are never touched, so admin edits survive every sync.
    """
    added: list[str] = []
    updated: list[str] = []
    now = datetime.now(timezone.utc)
    for rt in runtimes:
        arn = (rt.get("arn") or "").strip()
        if not arn:
            continue
        protocol = (rt.get("protocol") or "").strip()
        entry = await get_by_arn(db, arn)
        if entry is None:
            # Only auto-register AG-UI agents (per the requirement).
            if protocol.upper() != "AGUI":
                continue
            agent_id = await _unique_agent_id(db, _slugify(rt.get("name") or arn.split("/")[-1]))
            db.add(
                AgentCatalogEntry(
                    agent_id=agent_id,
                    display_name=rt.get("name") or agent_id,
                    description="",
                    ui_mode="a2ui",  # default for newly discovered agents
                    enabled=True,
                    runtime_arn=arn,
                    runtime_name=rt.get("name") or "",
                    protocol=protocol,
                    status=rt.get("status") or "",
                    version=str(rt.get("version") or ""),
                    last_synced_at=now,
                )
            )
            added.append(agent_id)
        else:
            # Refresh read-only synced fields only; never touch editable fields.
            entry.runtime_name = rt.get("name") or entry.runtime_name
            entry.protocol = protocol or entry.protocol
            entry.status = rt.get("status") or entry.status
            entry.version = str(rt.get("version") or entry.version)
            entry.last_synced_at = now
            updated.append(entry.agent_id)
    await db.commit()
    return {"added": added, "updated": updated}


async def update_entry(db: AsyncSession, agent_id: str, patch: dict) -> AgentCatalogEntry | None:
    """Apply an edit. Only EDITABLE_FIELDS are honoured (callers should reject
    read-only fields upstream for a clear error, but this is the last line)."""
    entry = await get_by_agent_id(db, agent_id)
    if entry is None:
        return None
    for key, value in patch.items():
        if key not in EDITABLE_FIELDS:
            continue
        if key == "ui_mode" and value not in UI_MODES:
            continue
        # Booleans arrive over JSON and can be anything the caller sent; coerce so
        # a string "false" cannot land in the column as a truthy value.
        if key in ("enabled", "accepts_files"):
            value = bool(value)
        setattr(entry, key, value)
    await db.commit()
    await db.refresh(entry)
    return entry
