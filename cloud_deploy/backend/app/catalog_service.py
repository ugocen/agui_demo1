"""Agent-catalog persistence + AgentCore sync.

The catalog is the platform's own registry of agents. AgentCore tells us what is
*deployed* (ARN, protocol, status, version); the catalog adds what AgentCore does
not know (display name, description, ui_mode, enabled) and is where the admin
screen edits live. The two are joined by `runtime_arn`.
"""

import os
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EDITABLE_FIELDS, UI_MODES, AgentCatalogEntry


def _seed_specs() -> list[dict]:
    """The agents that ship with the platform. Seeded as `static` — they use the
    hand-authored cards. ARNs come from .env; entries with no ARN are skipped."""
    return [
        {
            "agent_id": "planner",
            "display_name": "SDLC Planner",
            "description": "Backlog refinement and sprint planning assistant",
            "runtime_arn": os.environ.get("PLANNER_RUNTIME_ARN", ""),
        },
        {
            "agent_id": "release",
            "display_name": "Release Readiness",
            "description": "Pre-deployment release readiness assessment",
            "runtime_arn": os.environ.get("RELEASE_RUNTIME_ARN", ""),
        },
        {
            "agent_id": "bugreport",
            "display_name": "Bug Report Assistant",
            "description": "Turns a description into a structured, editable bug report",
            "runtime_arn": os.environ.get("BUGREPORT_RUNTIME_ARN", ""),
        },
        {
            "agent_id": "pressrelease",
            "display_name": "Press Release Assistant",
            "description": "Writes and revises a press release with editable cards + a document canvas",
            "runtime_arn": os.environ.get("PRESSRELEASE_RUNTIME_ARN", ""),
        },
    ]


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


async def seed_defaults(db: AsyncSession) -> None:
    """Idempotently seed the built-in agents as `static` (they use the polished
    hand-authored cards). Runs on startup; existing entries are left untouched."""
    changed = False
    for spec in _seed_specs():
        if not spec["runtime_arn"]:
            continue
        if await get_by_agent_id(db, spec["agent_id"]) or await get_by_arn(db, spec["runtime_arn"]):
            continue
        db.add(
            AgentCatalogEntry(
                agent_id=spec["agent_id"],
                display_name=spec["display_name"],
                description=spec["description"],
                ui_mode="static",
                enabled=True,
                runtime_arn=spec["runtime_arn"],
            )
        )
        changed = True

    # Purpose-built A2UI demo agent — only when wired to a local process via
    # LOCAL_AGENT_URL_A2UIDEMO. Seeded as ui_mode=a2ui with a placeholder ARN
    # (the proxy uses the LOCAL_AGENT_URL override, not the ARN).
    a2uidemo_arn = os.environ.get("A2UIDEMO_RUNTIME_ARN", "").strip()
    if (a2uidemo_arn or os.environ.get("LOCAL_AGENT_URL_A2UIDEMO")) and not await get_by_agent_id(db, "a2uidemo"):
        db.add(
            AgentCatalogEntry(
                agent_id="a2uidemo",
                display_name="A2UI Demo",
                description="Generative-UI demo agent — answers as A2UI surfaces",
                ui_mode="a2ui",
                enabled=True,
                # Deployed ARN when set (routes via SigV4); else a placeholder for the
                # local LOCAL_AGENT_URL_A2UIDEMO override.
                runtime_arn=a2uidemo_arn or "local:a2uidemo",
                protocol="AGUI",
                status="LOCAL" if not a2uidemo_arn else "",
            )
        )
        changed = True

    # Press-release agent — static cards. Seedable via LOCAL_AGENT_URL_PRESSRELEASE
    # (local run) even before it has a deployed ARN.
    pressrelease_arn = os.environ.get("PRESSRELEASE_RUNTIME_ARN", "").strip()
    if (
        (pressrelease_arn or os.environ.get("LOCAL_AGENT_URL_PRESSRELEASE"))
        and not await get_by_agent_id(db, "pressrelease")
    ):
        db.add(
            AgentCatalogEntry(
                agent_id="pressrelease",
                display_name="Press Release Assistant",
                description="Writes and revises a press release with editable cards + a document canvas",
                ui_mode="static",
                enabled=True,
                runtime_arn=pressrelease_arn or "local:pressrelease",
                protocol="AGUI",
                status="LOCAL" if not pressrelease_arn else "",
            )
        )
        changed = True

    if changed:
        await db.commit()


async def sync_from_agentcore(db: AsyncSession, runtimes: list[dict]) -> dict:
    """Upsert from live discovery.

    New **AG-UI** runtimes are auto-registered with `ui_mode='a2ui'` (the default
    for freshly discovered agents). Existing entries only get their AgentCore-sourced
    (read-only) fields refreshed — editable platform fields are never touched here.
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
        setattr(entry, key, value)
    await db.commit()
    await db.refresh(entry)
    return entry
