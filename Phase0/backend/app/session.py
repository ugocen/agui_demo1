"""Session endpoint: the frontend's source of truth for identity and roles.

The SPA calls GET /api/me after sign-in to learn *the backend's* view of who it
is and what roles it has. Roles are computed server-side from live AD-group
membership — the client never asserts its own roles for authorization, it only
mirrors this response for UI (showing/hiding nav and actions).
"""

from fastapi import APIRouter, Depends

from app.auth import require_user

router = APIRouter()


@router.get("/api/me")
async def me(user: dict = Depends(require_user)) -> dict:
    return {
        "mode": user["mode"],
        "authenticated": user["mode"] == "entra" and user["oid"] is not None,
        "user": user["user"],
        "oid": user["oid"],
        "email": user["email"],
        "roles": user["roles"],
    }
