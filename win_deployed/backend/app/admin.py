"""Admin API — platform settings. Section one: the agent catalog.

Everything here is gated to the `admin` role (default-deny via require_roles).
In iam mode (SSO off) the guard is a no-op so the admin screen works in local dev.

Read-only, AgentCore-sourced fields (ARN, name, protocol, status, version) cannot
be edited — a PATCH that touches them is rejected. New AG-UI agents discovered by
`/catalog/sync` are added with ui_mode='a2ui' by default; switch them to 'static'
here whenever you want.

Every mutating action (sync, edit) is written to the `audit_log` table with the
acting Entra ID identity.
"""

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents_catalog import discover_runtimes
from app.audit_service import list_audit, record_audit
from app.auth import require_roles
from app.catalog_service import list_entries, sync_from_agentcore, update_entry
from app.db import get_session
from app.models import EDITABLE_FIELDS, UI_MODES

# One dependency object, used both to gate the router and to inject the acting
# user into handlers. Reusing the same object lets FastAPI evaluate it once per
# request (a fresh require_roles("admin") would authenticate twice).
admin_dep = require_roles("admin")

router = APIRouter(prefix="/api/admin", dependencies=[Depends(admin_dep)])


@router.get("/catalog")
async def get_catalog(db: AsyncSession = Depends(get_session)) -> list[dict]:
    return [e.to_dict() for e in await list_entries(db)]


@router.post("/catalog/sync")
async def sync_catalog(
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(admin_dep),
) -> dict:
    """Pull live runtimes from AgentCore and reconcile the catalog."""
    result = await sync_from_agentcore(db, discover_runtimes())
    await record_audit(db, actor=user, action="catalog.sync", detail=result)
    return {"result": result, "catalog": [e.to_dict() for e in await list_entries(db)]}


@router.patch("/catalog/{agent_id}")
async def patch_catalog(
    agent_id: str,
    patch: dict = Body(...),
    db: AsyncSession = Depends(get_session),
    user: dict = Depends(admin_dep),
) -> dict:
    unknown = set(patch) - EDITABLE_FIELDS
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"these fields are read-only / not editable: {sorted(unknown)}",
        )
    if "ui_mode" in patch and patch["ui_mode"] not in UI_MODES:
        raise HTTPException(status_code=400, detail=f"ui_mode must be one of {sorted(UI_MODES)}")

    entry = await update_entry(db, agent_id, patch)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown agent {agent_id}")
    await record_audit(db, actor=user, action="catalog.update", target=agent_id, detail=patch)
    return entry.to_dict()


@router.get("/audit")
async def get_audit(
    limit: int = 200,
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    """The audit trail, newest first. Admin-gated like the rest of this router."""
    limit = max(1, min(limit, 1000))
    return [e.to_dict() for e in await list_audit(db, limit=limit)]
