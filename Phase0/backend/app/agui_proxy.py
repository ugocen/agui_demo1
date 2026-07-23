"""AG-UI proxy.

POST /api/agui/{agent_id} looks up the agent in the DB catalog (populated from
AgentCore, never from env), forwards the AG-UI request to that runtime's
AgentCore invocation endpoint, and pipes the SSE stream back unchanged. httpx
streaming, no buffering.

HOW THE UPSTREAM CALL IS AUTHENTICATED
--------------------------------------
Per the catalog entry's `inbound_auth`, which is synced from the runtime's own
authorizerConfiguration — never guessed here, because guessing wrong means every
request to that agent is signed the wrong way:

* **iam** (all the original agents) — SigV4 with the host's AWS credentials. The
  caller's Entra token was validated at the platform boundary and stops there;
  the backend calls AgentCore as the trusted caller, and the agent never learns
  who asked.
* **jwt** (whoami-strands) — no SigV4 at all. The caller's own Entra token is
  forwarded as the bearer and AgentCore validates it against the tenant's OIDC
  discovery document before the agent's container is reached. That token is NOT
  the platform's bearer: the SPA sends the platform a Microsoft Graph access
  token, which no OIDC authorizer can validate (see app/auth.py), so the browser
  sends a second, tenant-issued token in `X-Agent-Authorization` and that is what
  is signed with. Note that authenticating the call is ALL the bearer does: the
  authorizer consumes it, so agent code never sees it (see the relay below).

Layer B (backend -> AgentCore) is therefore no longer "always SigV4" — it is
"always what the runtime is configured to accept". Layer A (browser -> backend)
is untouched: every route still goes through `require_platform_access`, so a JWT
agent is not a way around platform sign-in.

Optionally (AGENT_TOKEN_RELAY=1) the caller's tokens are also passed to the agent
in AgentCore's custom forwardable headers. This is the ONLY way an agent learns
who is asking — under iam because nothing else carries the caller, and under jwt
because the authorizer consumes the bearer before the container is reached — and
it is also what gives the agent a Graph token when no AgentCore Identity OBO
provider is configured. Off by default: it hands a delegated user token to the
runtime, and no other agent has any use for one.
"""

import json
import os
import urllib.parse
import uuid

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents_catalog import get_agent
from app.auth import require_platform_access
from app.db import get_session
from app.logging_setup import get_logger

router = APIRouter()
log = get_logger("proxy")

SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"
MIN_SESSION_ID_LENGTH = 33

# The browser's second token: tenant-issued (an Entra ID token by default), the
# one an OIDC authorizer can actually verify. Sent alongside the platform's own
# Authorization header, never instead of it.
AGENT_TOKEN_HEADER = "X-Agent-Authorization"

# AgentCore forwards headers with this prefix — and only this prefix, out of
# everything starting with `x-amzn-` — to the agent's container. Anything else we
# invented would be silently dropped in transit.
ID_TOKEN_RELAY_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Id-Token"
GRAPH_TOKEN_RELAY_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Graph-Token"


def token_relay_enabled() -> bool:
    return os.environ.get("AGENT_TOKEN_RELAY", "").strip().lower() in ("1", "true", "yes", "on")


def _bearer(value: str) -> str:
    value = (value or "").strip()
    if value.lower().startswith("bearer "):
        return value.split(" ", 1)[1].strip()
    return value


def agent_token(request: Request | None) -> str:
    """The tenant-issued token meant for AgentCore, from `X-Agent-Authorization`.

    Deliberately does NOT fall back to the platform's Authorization header. That
    header carries a Microsoft Graph access token, which AgentCore's JWT
    authorizer rejects — a first-party resource token cannot be validated against
    the tenant JWKS — and the resulting upstream 403 says nothing about the real
    cause. An empty string here produces an error that names the missing header.
    """
    if request is None:
        return ""
    return _bearer(request.headers.get(AGENT_TOKEN_HEADER, ""))


def upstream_auth_headers(
    *,
    agent: dict,
    request: Request | None,
    user: dict,
    url: str,
    body: bytes,
    region: str,
    base_headers: dict,
) -> dict:
    """Authenticate the AgentCore call the way this runtime expects, plus relays."""
    headers = dict(base_headers)
    inbound_auth = (agent.get("inbound_auth") or "iam").lower()

    if token_relay_enabled():
        # The agent's *own* view of the caller, in headers AgentCore forwards.
        # Both are optional and independent: an agent that gets neither reports
        # the caller as anonymous rather than failing.
        graph_token = _bearer(user.get("token") or "")
        if graph_token:
            headers[GRAPH_TOKEN_RELAY_HEADER] = graph_token
        entra_token = agent_token(request)
        if entra_token:
            # Relayed under jwt TOO, and that is not redundancy. AgentCore's JWT
            # authorizer CONSUMES the Authorization header: it validates the
            # bearer at the front door and the container never sees it, so an
            # agent behind jwt inbound auth reads no caller at all unless the
            # token also arrives in a forwardable custom header. Observed
            # 2026-07-23 — a run that AgentCore had accepted (the runtime is
            # JWT-only, so the bearer was valid by construction) still reported
            # `auth.token_source: none` from inside the container.
            headers[ID_TOKEN_RELAY_HEADER] = entra_token

    if inbound_auth != "jwt":
        return sigv4_headers(url, body, region, headers)

    token = agent_token(request)
    if not token:
        raise HTTPException(
            status_code=401,
            detail=(
                f"agent {agent['id']} runs on a JWT-authorized AgentCore runtime and needs the "
                f"caller's Entra token in the {AGENT_TOKEN_HEADER} header. None arrived — sign in "
                "with Entra (AUTH_MODE=entra on the backend and the frontend); with SSO off there "
                "is no user token to forward."
            ),
        )
    headers["Authorization"] = f"Bearer {token}"
    return headers


def invocation_url(runtime_arn: str, region: str) -> str:
    escaped_arn = urllib.parse.quote(runtime_arn, safe="")
    return (
        f"https://bedrock-agentcore.{region}.amazonaws.com"
        f"/runtimes/{escaped_arn}/invocations?qualifier=DEFAULT"
    )


def session_id_from_thread(body: bytes) -> str:
    try:
        thread_id = str(json.loads(body).get("threadId") or "")
    except (ValueError, AttributeError):
        thread_id = ""
    session_id = thread_id or "phase0-session"
    if len(session_id) < MIN_SESSION_ID_LENGTH:
        session_id = session_id + "-" + "0" * MIN_SESSION_ID_LENGTH
    return session_id[:100]


def sigv4_headers(url: str, body: bytes, region: str, base_headers: dict) -> dict:
    """SigV4-sign the upstream AgentCore call with the host's AWS credentials.

    Credentials here are usually a short-lived `aws login` session, so resolving
    them FAILS as a matter of course once it expires: botocore raises
    LoginRefreshRequired (a BotoCoreError) out of `get_frozen_credentials()`.
    Uncaught, that left FastAPI to return its bare-text 500 — which, being raised
    outside CORSMiddleware, reaches the browser with no CORS headers and shows up
    as an opaque `TypeError: Failed to fetch`. Every agent looked broken and the
    one thing the user had to do was invisible. Convert it to a 503 that says so.
    """
    try:
        credentials = boto3.Session().get_credentials()
        if credentials is None:
            raise HTTPException(
                status_code=503,
                detail="no AWS credentials available for SigV4 — sign in with `aws login`",
            )
        frozen = credentials.get_frozen_credentials()
    except (BotoCoreError, ClientError) as error:
        raise HTTPException(
            status_code=503,
            detail=f"AWS credentials unavailable — re-authenticate with `aws login` ({type(error).__name__}: {error})",
        )
    aws_request = AWSRequest(method="POST", url=url, data=body, headers=base_headers)
    SigV4Auth(frozen, "bedrock-agentcore", region).add_auth(aws_request)
    return dict(aws_request.headers)


@router.post("/api/agui/{agent_id}")
async def proxy_agui(
    agent_id: str,
    request: Request,
    user: dict = Depends(require_platform_access),
    db: AsyncSession = Depends(get_session),
):
    agent = await get_agent(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"unknown agent {agent_id}")

    body = await request.body()
    session_id = session_id_from_thread(body)
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        SESSION_HEADER: session_id,
    }
    log.debug(
        "proxy %s: auth_mode=%s user=%s session=%s body=%dB",
        agent_id,
        user.get("mode"),
        user.get("user", "-"),
        session_id[:16],
        len(body),
    )

    # The runtime ARN comes from the DB catalog entry (synced from AgentCore),
    # never from env. An empty ARN means the catalog is stale / the runtime was
    # removed from AgentCore — re-sync to fix.
    runtime_arn = agent["runtime_arn"]
    if not runtime_arn:
        raise HTTPException(
            status_code=503,
            detail=f"agent {agent_id} has no AgentCore runtime ARN in the catalog — re-sync the catalog",
        )
    region = os.environ.get("AWS_REGION", "")
    if not region:
        raise HTTPException(status_code=500, detail="AWS_REGION is not set")
    url = invocation_url(runtime_arn, region)
    # SigV4 or the caller's own bearer, per the runtime's inbound auth — see the
    # module docstring. Layer A has already run (require_platform_access), so by
    # here the caller is a signed-in platform user either way.
    headers = upstream_auth_headers(
        agent=agent, request=request, user=user, url=url, body=body, region=region, base_headers=headers
    )
    log.debug(
        "proxy %s -> AgentCore (%s) %s",
        agent_id,
        "user JWT" if (agent.get("inbound_auth") == "jwt") else "SigV4",
        url.split("?")[0],
    )

    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=None, write=30, pool=10))
    upstream_request = client.build_request("POST", url, content=body, headers=headers)
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as error:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"upstream connection failed: {error}")

    if upstream.status_code != 200:
        detail = (await upstream.aread()).decode(errors="replace")
        await upstream.aclose()
        await client.aclose()
        log.warning("proxy %s upstream returned %s: %s", agent_id, upstream.status_code, detail[:200])
        raise HTTPException(status_code=upstream.status_code, detail=detail[:1000])

    log.debug("proxy %s upstream 200, streaming SSE back", agent_id)

    async def pipe():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    media_type = upstream.headers.get("content-type", "text/event-stream")
    return StreamingResponse(pipe(), media_type=media_type)


@router.get("/api/agui/{agent_id}/health")
async def agui_health(
    agent_id: str,
    request: Request,
    user: dict = Depends(require_platform_access),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Liveness probe for one agent — is its runtime actually up?

    The control plane reports a runtime READY even when its container cannot
    boot (the port bug of 2026-07-15 sat behind a READY runtime), so the only
    truthful check is a real invoke. This opens an AG-UI run and stops at the
    first event: RUN_STARTED is emitted before the model is called, so reaching
    it proves the whole path (catalog -> proxy -> SigV4 -> AgentCore -> the
    container booted -> the agent started) at near-zero token cost.

    Unlike the proxy route, this returns JSON (not an SSE stream) and reads only
    the first event, so it does not stream to the browser and does not violate
    the "never buffer the proxy" invariant — it is a separate liveness endpoint.
    """
    agent = await get_agent(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"unknown agent {agent_id}")

    runtime_arn = agent["runtime_arn"]
    if not runtime_arn:
        return {
            "agent_id": agent_id,
            "alive": False,
            "detail": "no AgentCore runtime ARN in the catalog — re-sync the catalog",
        }
    region = os.environ.get("AWS_REGION", "")
    if not region:
        raise HTTPException(status_code=500, detail="AWS_REGION is not set")

    payload = {
        "threadId": f"health-{uuid.uuid4().hex}",
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "messages": [{"id": f"msg-{uuid.uuid4().hex[:8]}", "role": "user", "content": "ping"}],
        "tools": [],
        "context": [],
        "state": {},
        "forwardedProps": {},
    }
    body = json.dumps(payload).encode()
    session_id = session_id_from_thread(body)
    base_headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        SESSION_HEADER: session_id,
    }
    url = invocation_url(runtime_arn, region)
    # This endpoint answers "is the agent up?" with a verdict, and the banner is
    # the only place the user ever sees it — so report a local credential failure,
    # or a JWT agent with no caller token, as the verdict's detail rather than
    # raising it into an opaque fetch error.
    try:
        headers = upstream_auth_headers(
            agent=agent,
            request=request,
            user=user,
            url=url,
            body=body,
            region=region,
            base_headers=base_headers,
        )
    except HTTPException as error:
        return {"agent_id": agent_id, "alive": False, "detail": str(error.detail)}

    # AgentCore takes ~30s to give up on an unhealthy runtime; read generously so
    # that verdict is captured rather than the request timing out first.
    timeout = httpx.Timeout(connect=10, read=60, write=30, pool=10)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, content=body, headers=headers) as upstream:
                if upstream.status_code != 200:
                    detail = (await upstream.aread()).decode(errors="replace")
                    return {"agent_id": agent_id, "alive": False, "detail": f"HTTP {upstream.status_code}: {detail[:200]}"}
                async for line in upstream.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except ValueError:
                        continue
                    etype = event.get("type")
                    if etype == "RUN_STARTED":
                        return {"agent_id": agent_id, "alive": True, "detail": "container booted, agent running"}
                    if etype == "RUN_ERROR":
                        return {"agent_id": agent_id, "alive": False, "detail": (event.get("message") or "RUN_ERROR")[:220]}
                return {"agent_id": agent_id, "alive": False, "detail": "stream closed without RUN_STARTED"}
    except httpx.HTTPError as error:
        return {"agent_id": agent_id, "alive": False, "detail": f"{type(error).__name__}: {error}"}
