"""Bearer authentication for the local backend (Entra ID SSO).

This follows the AI SDLC platform's SSO *method* — a Microsoft Graph delegated
access token is forwarded by the SPA and the backend resolves identity and
AD-group membership from Graph — but hardened so it does NOT repeat that system's
mistakes.

Flow (AUTH_MODE=entra)
----------------------
1. The SPA acquires a delegated **Graph access token** (scope ``User.Read``) and
   sends it as ``Authorization: Bearer``. The backend never forwards this token
   upstream to AgentCore (that call stays SigV4 — auth is two independent layers);
   it is used only at the platform boundary.
2. Local pre-checks on the (unverified) claims reject obviously-wrong tokens
   early: tenant (``tid``), authorized party (``azp``/``appid``), audience
   (must be Microsoft Graph) and the temporal claims (``exp``/``nbf``) with a
   small clock-skew leeway.
3. **Authoritative** authenticity: call Graph ``/me`` with the token. A Graph
   access token is a first-party resource token (``aud`` = Graph, its header
   carries a ``nonce``) and cannot be signature-verified against the tenant JWKS
   by anyone but Graph — so the live ``/me`` call, which rejects invalid, expired
   or revoked tokens, is the real check. Results are cached briefly per token so
   we do not hit Graph on every request.
4. **Authorization**: resolve the caller's AD-group membership with a single
   targeted ``/me/checkMemberGroups`` against the group ids we care about
   (``ENTRA_GROUP_ROLE_MAP`` + ``ENTRA_ADMIN_GROUP_ID``) and map them to platform
   roles. Fail-closed: any Graph failure yields no roles. Cached per user.

Why hardened vs. the source system
-----------------------------------
The source accepted tokens from any tenant and any client app (any Graph token
worked — a confused-deputy), had a default mode that skipped verification
entirely, and derived authorization from a default-allow middleware. Here we pin
``tid`` (no cross-tenant), pin ``azp``/``appid`` to the allowed SPA client (no
confused-deputy), and every protected route is default-**deny** via
``require_platform_access`` / ``require_roles``. Roles are never trusted from the
client — they are computed here from live group membership.

AUTH_MODE
---------
``iam`` / ``off`` (default): SSO disabled — no validation, no roles, behaves like
the pre-SSO backend so the app can run and be developed locally without a real
Microsoft login. ``entra``: full SSO + role resolution.

If no group→role config is present, identity is still validated but no role is
derived (identity-only), mirroring the previous ``REQUIRED_ROLE`` empty behaviour.
Every decision is logged so the SSO flow can be traced end to end.
"""

import hashlib
import json
import os
import time
from urllib.parse import quote

import httpx
import jwt
from fastapi import Depends, Header, HTTPException

from app.logging_setup import get_logger

log = get_logger("auth")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# A Microsoft Graph access token carries one of these as its `aud`.
GRAPH_AUDIENCES = {"https://graph.microsoft.com", "00000003-0000-0000-c000-000000000000"}
CLOCK_SKEW_LEEWAY = 60  # seconds


# --- tiny in-process TTL cache (identity + group membership) -----------------
# Keeps us off Graph on every request without pulling in Redis for a spike.
_cache: dict[str, tuple[float, object]] = {}


def _cache_get(key: str):
    item = _cache.get(key)
    if item is None:
        return None
    expires_at, value = item
    if time.time() >= expires_at:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: object, ttl_seconds: int) -> None:
    _cache[key] = (time.time() + ttl_seconds, value)


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- configuration (read at call time so env overrides always apply) ---------
def auth_mode() -> str:
    return os.environ.get("AUTH_MODE", "iam").strip().lower()


def _allowed_client_ids() -> set[str]:
    """Client ids permitted as the token's `azp`/`appid` (confused-deputy guard).

    Defaults to the SPA client id when the dedicated list is not set.
    """
    raw = os.environ.get("ENTRA_ALLOWED_CLIENT_IDS", "").strip()
    if not raw:
        raw = os.environ.get("ENTRA_SPA_CLIENT_ID", "").strip()
    return {c.strip() for c in raw.split(",") if c.strip()}


def _group_role_map() -> dict[str, str]:
    """{AD group object id: role name}. Group ids are matched exactly (they are
    opaque GUIDs), so no case/whitespace ambiguity — unlike matching display names."""
    raw = os.environ.get("ENTRA_GROUP_ROLE_MAP", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.error("ENTRA_GROUP_ROLE_MAP is not valid JSON; ignoring (no group roles)")
        return {}
    if not isinstance(parsed, dict):
        log.error("ENTRA_GROUP_ROLE_MAP must be a JSON object; ignoring")
        return {}
    return {str(k).strip(): str(v).strip() for k, v in parsed.items() if str(k).strip()}


def _admin_group_id() -> str:
    return os.environ.get("ENTRA_ADMIN_GROUP_ID", "").strip()


def _admin_group_name() -> str:
    return os.environ.get("ENTRA_ADMIN_GROUP_NAME", "").strip()


def _interested_group_ids() -> list[str]:
    ids = set(_group_role_map().keys())
    admin = _admin_group_id()
    if admin:
        ids.add(admin)
    return sorted(ids)


def _groups_ttl_seconds() -> int:
    try:
        return int(os.environ.get("ENTRA_GROUPS_TTL_SECONDS", "300"))
    except ValueError:
        return 300


def _bootstrap_admin_emails() -> set[str]:
    """Emails granted the `admin` role directly, without an AD group. A bootstrap
    escape hatch (e.g. before groups are set up, or on a test tenant)."""
    raw = os.environ.get("ENTRA_ADMIN_EMAILS", "")
    return {e.strip().casefold() for e in raw.split(",") if e.strip()}


def _bootstrap_admin_oids() -> set[str]:
    raw = os.environ.get("ENTRA_ADMIN_OIDS", "")
    return {o.strip() for o in raw.split(",") if o.strip()}


def _is_bootstrap_admin(email: str | None, oid: str | None) -> bool:
    return bool(
        (email and email.casefold() in _bootstrap_admin_emails())
        or (oid and oid in _bootstrap_admin_oids())
    )


# --- token claim pre-checks --------------------------------------------------
def _claims_unverified(token: str) -> dict:
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as error:
        log.warning("rejecting malformed token: %s", error)
        raise HTTPException(status_code=401, detail=f"malformed token: {error}")


def _check_local_claims(claims: dict) -> None:
    """Cheap, fail-fast checks before we spend a Graph round-trip.

    These are defence-in-depth; the Graph /me call is still authoritative.
    """
    now = int(time.time())

    exp = claims.get("exp")
    if exp is None or now > int(exp) + CLOCK_SKEW_LEEWAY:
        raise HTTPException(status_code=401, detail="token expired")
    nbf = claims.get("nbf")
    if nbf is not None and now + CLOCK_SKEW_LEEWAY < int(nbf):
        raise HTTPException(status_code=401, detail="token not yet valid")

    # Single-tenant pin — MANDATORY in entra mode. If the tenant is not configured
    # we refuse every request (fail closed) rather than silently accepting tokens
    # from any tenant. Guarding on `if tenant` here would be a fail-open on missing
    # config — exactly the class of mistake this port avoids.
    tenant = os.environ.get("ENTRA_TENANT_ID", "").strip()
    if not tenant:
        log.error("AUTH_MODE=entra but ENTRA_TENANT_ID is empty — refusing all requests (fail closed)")
        raise HTTPException(status_code=500, detail="server misconfigured: ENTRA_TENANT_ID is required in entra mode")
    if claims.get("tid") != tenant:
        log.warning("rejecting token from tenant %s (expected %s)", claims.get("tid"), tenant)
        raise HTTPException(status_code=401, detail="token issued for a different tenant")

    # Must be a Microsoft Graph token (this is what we call /me with).
    if claims.get("aud") not in GRAPH_AUDIENCES:
        log.warning("rejecting token with non-Graph audience: %s", claims.get("aud"))
        raise HTTPException(status_code=401, detail="token audience is not Microsoft Graph")

    # Authorized-party pin — MANDATORY in entra mode. Rejects a Graph token minted
    # for some *other* app the user consented to (confused-deputy). If no allowed
    # client id is configured we refuse (fail closed), never accept-any-client.
    allowed = _allowed_client_ids()
    if not allowed:
        log.error(
            "AUTH_MODE=entra but no allowed client id (ENTRA_SPA_CLIENT_ID / "
            "ENTRA_ALLOWED_CLIENT_IDS) — refusing all requests (fail closed)"
        )
        raise HTTPException(
            status_code=500,
            detail="server misconfigured: ENTRA_SPA_CLIENT_ID or ENTRA_ALLOWED_CLIENT_IDS is required in entra mode",
        )
    azp = claims.get("azp") or claims.get("appid")
    if azp not in allowed:
        log.warning("rejecting token from client %s (allowed: %s)", azp, allowed)
        raise HTTPException(status_code=401, detail="token was not issued to an allowed client")


# --- Microsoft Graph calls ---------------------------------------------------
async def _graph_me(token: str) -> dict:
    """Authoritative identity + authenticity check. Cached briefly per token."""
    key = "me:" + _token_fingerprint(token)
    cached = _cache_get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    url = f"{GRAPH_BASE}/me?$select=id,displayName,userPrincipalName,mail,givenName,surname"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
            )
    except httpx.HTTPError as error:
        log.error("Graph /me request failed: %s", error)
        raise HTTPException(status_code=401, detail="identity check failed")

    if resp.status_code != 200:
        log.warning("Graph /me rejected token: %s %s", resp.status_code, resp.text[:200])
        raise HTTPException(status_code=401, detail="invalid or expired token")

    profile = resp.json()
    _cache_set(key, profile, 60)
    return profile


async def _graph_member_groups(token: str, oid: str, group_ids: list[str]) -> set[str]:
    """Which of `group_ids` the caller belongs to (transitive). Fail-closed."""
    if not group_ids:
        return set()

    key = "groups:" + oid
    cached = _cache_get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    url = f"{GRAPH_BASE}/me/checkMemberGroups"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"groupIds": group_ids},
            )
    except httpx.HTTPError as error:
        log.error("Graph checkMemberGroups failed: %s (failing closed)", error)
        return set()

    if resp.status_code != 200:
        log.warning("Graph checkMemberGroups %s: %s (failing closed)", resp.status_code, resp.text[:200])
        return set()

    member_ids = {str(g) for g in (resp.json().get("value") or [])}
    _cache_set(key, member_ids, _groups_ttl_seconds())
    return member_ids


async def _graph_is_member_of_group_name(token: str, group_name: str, oid: str | None) -> bool:
    """True if the caller is a (transitive) member of the AD group with this exact
    display name — how AI SDLC referenced groups, but hardened.

    Uses one targeted Graph query with a server-side **exact** `displayName eq`
    filter (no substring/case bug), $count for advanced query, $top=1. Fail-closed,
    cached per (user, group name).
    """
    target = group_name.strip()
    if not target:
        return False

    cache_key = f"adgroup_name:{oid or ''}:{target.casefold()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return bool(cached)

    odata_value = target.replace("'", "''")  # escape single quotes per OData
    filter_expr = quote(f"displayName eq '{odata_value}'", safe="")
    url = (
        f"{GRAPH_BASE}/me/transitiveMemberOf/microsoft.graph.group"
        f"?$filter={filter_expr}&$count=true&$top=1&$select=id"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    # Advanced query is required to $filter directory objects by displayName.
                    "ConsistencyLevel": "eventual",
                },
            )
    except httpx.HTTPError as error:
        log.warning("Graph group-name membership check failed: %s (failing closed)", error)
        return False

    if resp.status_code != 200:
        log.warning("Graph group-name membership %s: %s (failing closed)", resp.status_code, resp.text[:200])
        return False

    value = resp.json().get("value") or []
    is_member = isinstance(value, list) and len(value) > 0
    _cache_set(cache_key, is_member, _groups_ttl_seconds())
    return is_member


def _roles_from_groups(member_ids: set[str]) -> list[str]:
    roles: set[str] = set()
    for group_id, role in _group_role_map().items():
        if group_id in member_ids:
            roles.add(role)
    admin = _admin_group_id()
    if admin and admin in member_ids:
        roles.add("admin")
    return sorted(roles)


# --- FastAPI dependencies ----------------------------------------------------
def _anonymous(mode: str) -> dict:
    return {"mode": mode, "user": None, "oid": None, "email": None, "roles": [], "token": None, "claims": None}


async def require_user(authorization: str | None = Header(default=None)) -> dict:
    """Authenticate the caller and attach their platform roles.

    Does NOT enforce any role by itself, so /api/me can report a user's roles.
    Route-level enforcement is done with `require_platform_access` / `require_roles`.
    """
    mode = auth_mode()
    if mode in ("iam", "off", ""):
        log.debug("auth mode=%s, skipping SSO", mode or "unset")
        return _anonymous("iam")
    if mode != "entra":
        log.warning("unknown AUTH_MODE=%s; treating as iam (SSO off)", mode)
        return _anonymous("iam")

    if not authorization or not authorization.lower().startswith("bearer "):
        log.warning("rejecting request: no bearer token present")
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="empty bearer token")

    claims = _claims_unverified(token)
    _check_local_claims(claims)

    profile = await _graph_me(token)
    oid = profile.get("id")
    email = profile.get("mail") or profile.get("userPrincipalName")
    display_name = profile.get("displayName") or email or oid

    member_ids = await _graph_member_groups(token, oid or "", _interested_group_ids())
    roles = _roles_from_groups(member_ids)

    # Admin via a named AD group (resolved by display name) — the AI SDLC style,
    # in addition to the object-id ENTRA_ADMIN_GROUP_ID handled above.
    admin_group_name = _admin_group_name()
    if admin_group_name and "admin" not in roles and await _graph_is_member_of_group_name(
        token, admin_group_name, oid
    ):
        roles = sorted([*roles, "admin"])

    # Bootstrap admin allowlist — grants `admin` by email/oid, independent of groups.
    if _is_bootstrap_admin(email, oid) and "admin" not in roles:
        roles = sorted([*roles, "admin"])

    log.debug("authenticated user=%s oid=%s roles=%s", email, oid, roles)
    return {
        "mode": "entra",
        "user": display_name,
        "oid": oid,
        "email": email,
        "roles": roles,
        "token": token,
        "claims": claims,
    }


def require_roles(*required_roles: str):
    """Route dependency factory enforcing at least one of `required_roles`.

    Default-deny: a user without a matching role gets 403. When SSO is off the
    check is a no-op (local dev). With no roles listed it only requires a valid
    identity.
    """

    async def _dependency(user: dict = Depends(require_user)) -> dict:
        if user["mode"] != "entra":
            return user
        if not required_roles:
            return user
        if not set(required_roles) & set(user["roles"]):
            log.warning(
                "denying user=%s: needs one of %s, has %s",
                user.get("email"),
                list(required_roles),
                user.get("roles"),
            )
            raise HTTPException(status_code=403, detail=f"missing required role: {list(required_roles)}")
        return user

    return _dependency


async def require_platform_access(user: dict = Depends(require_user)) -> dict:
    """Gate for using the platform. Enforces the optional REQUIRED_ROLE env.

    Empty REQUIRED_ROLE = any authenticated user may use the platform (identity
    only); set it to require a specific role (e.g. the group mapped to "user").
    """
    if user["mode"] != "entra":
        return user
    required = os.environ.get("REQUIRED_ROLE", "").strip()
    if required and required not in user["roles"]:
        log.warning("denying user=%s: missing REQUIRED_ROLE=%s (has %s)", user.get("email"), required, user.get("roles"))
        raise HTTPException(status_code=403, detail=f"missing required role: {required}")
    return user


def require_ad_group(group_name: str):
    """Route dependency factory enforcing membership in a named AD group.

    A reusable primitive (mirrors the AI SDLC platform) for gating any operation by
    AD group — attach with `dependencies=[Depends(require_ad_group("My-Group"))]`.
    Default-deny (403 if not a member); a no-op when SSO is off (iam mode).
    """

    async def _dependency(user: dict = Depends(require_user)) -> dict:
        if user["mode"] != "entra":
            return user
        token = user.get("token")
        if token and await _graph_is_member_of_group_name(token, group_name, user.get("oid")):
            return user
        log.warning("denying user=%s: not a member of AD group %s", user.get("email"), group_name)
        raise HTTPException(status_code=403, detail=f"forbidden: AD group required: {group_name}")

    return _dependency
