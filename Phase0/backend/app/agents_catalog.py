"""Phase 0 agent catalog (DB-backed).

GET /api/agents            — the platform's registered, enabled agents (from the DB
                             catalog), with their ui_mode.
GET /api/agentcore/runtimes — live discovery from the AgentCore control plane,
                             annotated with whether each ARN is registered.

The DB catalog is the source of truth for platform metadata (name, description,
ui_mode…); AgentCore is the source of truth for deployment (ARN, protocol, status).
They are joined by runtime ARN. Admin editing of the catalog lives in app/admin.py.
"""

import os

import boto3
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_platform_access
from app.catalog_service import get_by_agent_id, list_entries, sync_from_agentcore
from app.db import get_session

router = APIRouter()


def discover_runtimes() -> list[dict]:
    """Live list of every runtime deployed in the account/region, with protocol."""
    region = os.environ.get("AWS_REGION", "")
    if not region:
        raise HTTPException(status_code=500, detail="AWS_REGION is not set in .env")

    client = boto3.client("bedrock-agentcore-control", region_name=region)
    runtimes: list[dict] = []
    next_token = None
    while True:
        kwargs = {"maxResults": 100}
        if next_token:
            kwargs["nextToken"] = next_token
        try:
            page = client.list_agent_runtimes(**kwargs)
        except Exception as error:
            raise HTTPException(status_code=502, detail=f"AgentCore list failed: {error}")

        for runtime in page.get("agentRuntimes", []):
            protocol = ""
            try:
                detail = client.get_agent_runtime(agentRuntimeId=runtime["agentRuntimeId"])
                protocol = (detail.get("protocolConfiguration") or {}).get("serverProtocol", "")
            except Exception:
                pass
            last_updated = runtime.get("lastUpdatedAt")
            runtimes.append(
                {
                    "name": runtime.get("agentRuntimeName"),
                    "id": runtime.get("agentRuntimeId"),
                    "arn": runtime.get("agentRuntimeArn", ""),
                    "status": runtime.get("status"),
                    "version": runtime.get("agentRuntimeVersion"),
                    "protocol": protocol,
                    "last_updated": last_updated.isoformat() if last_updated else None,
                }
            )
        next_token = page.get("nextToken")
        if not next_token:
            break
    return runtimes


async def sync_catalog(db: AsyncSession) -> list[dict]:
    """Discover live AG-UI runtimes from AgentCore and upsert them into the DB
    catalog, then return those runtimes. This is the *only* path by which agents
    enter the catalog — there is no env/seed path, and the proxy routes purely on
    the DB entry's ARN. Non-AG-UI protocols (MCP, A2A, HTTP) are ignored.
    """
    runtimes = [r for r in discover_runtimes() if (r.get("protocol") or "").upper() == "AGUI"]
    await sync_from_agentcore(db, runtimes)
    return runtimes


async def get_agent(db: AsyncSession, agent_id: str) -> dict | None:
    """Resolve a registered, enabled agent for routing (used by the AG-UI proxy)."""
    entry = await get_by_agent_id(db, agent_id)
    if entry is None or not entry.enabled:
        return None
    return {
        "id": entry.agent_id,
        "name": entry.display_name,
        "runtime_arn": entry.runtime_arn,
        "ui_mode": entry.ui_mode,
        "required_role": entry.required_role,
    }


@router.get("/api/agents")
async def list_agents(
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(require_platform_access),
) -> list:
    entries = await list_entries(db, enabled_only=True)
    return [
        {
            "id": e.agent_id,
            "name": e.display_name,
            "description": e.description,
            "capability": "agui",
            "runtime_arn": e.runtime_arn,
            "ui_mode": e.ui_mode,
        }
        for e in entries
    ]


@router.get("/api/agentcore/runtimes")
async def list_agentcore_runtimes(
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(require_platform_access),
) -> list:
    # Discover AG-UI runtimes and auto-register them: newly-deployed agents are
    # added to the catalog (ui_mode=a2ui by default) and existing entries' read-only
    # fields refreshed — so a runtime added to AgentCore shows up here automatically,
    # no manual "Sync". Other protocols (MCP, A2A, HTTP) are ignored.
    runtimes = await sync_catalog(db)

    by_arn = {e.runtime_arn: e for e in await list_entries(db)}
    for runtime in runtimes:
        entry = by_arn.get(runtime["arn"])
        runtime["registered"] = entry is not None
        runtime["ui_mode"] = entry.ui_mode if entry else None
    return runtimes
