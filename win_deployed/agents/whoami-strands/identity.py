"""Who is calling? — inbound token -> verified claims -> Microsoft Graph profile.

This is the only file in the agent that knows anything about authentication. The
tools call it; the prompt never sees a token.

WHERE THE TOKEN COMES FROM
--------------------------
An AgentCore runtime has exactly ONE inbound auth mode, and that mode decides
what the container finds in the ``Authorization`` header:

* **JWT inbound auth** (``authorizerConfiguration.customJWTAuthorizer``, what
  ``deploy_agent.py --auth=jwt`` configures) — the caller sends
  ``Authorization: Bearer <Entra token>``, AgentCore validates it against the
  tenant's OIDC discovery document *before* the container is reached, and then
  forwards it **only if the runtime allowlists it**
  (``requestHeaderConfiguration.requestHeaderAllowlist``). That allowlist is the
  fact this file got wrong until 2026-07-23: NOTHING reaches agent code without
  it, so a run AgentCore had just authenticated resolved to
  ``token_source: none`` and this agent saw two platform-injected headers and no
  token. Not a restricted-header problem — ``Authorization`` is absent from that
  list and the SDK special-cases it — simply a header the runtime never asked for.
* **IAM / SigV4 inbound auth** (the default, and what the other agents use) — the
  same header carries the AWS signature, ``AWS4-HMAC-SHA256 Credential=…``. It is
  never a user token, so a value starting with ``AWS4-`` is ignored here. The
  platform proxy relays the caller's Entra tokens in the runtime's *custom*
  forwardable headers (``X-Amzn-Bedrock-AgentCore-Runtime-Custom-*``), which
  keeps this agent working on an IAM runtime — local dev, the smoke test, and
  any time before the JWT switch is made. Those need the same allowlist: the
  prefix makes a header eligible for it, never exempt from it.

Both paths end in the same place: a token, and where it came from.

HOW MUCH OF IT WE TRUST
-----------------------
Under JWT inbound auth AgentCore has already verified the signature, issuer and
audience — but "someone else checked it" is not a thing to build identity on when
the same code also runs behind SigV4, where nothing checked it. So the claims are
re-verified here against the tenant JWKS (RS256, issuer + audience + expiry, 60s
leeway) and every answer carries the verdict. A Microsoft Graph access token is
the one token that CANNOT be verified this way — it is a first-party resource
token whose header carries a ``nonce`` and which only Graph can validate — so for
that one the live ``/me`` call is the authoritative check, exactly as the
backend's ``app/auth.py`` documents.

PERSON INFORMATION
------------------
Two levels, and the tools report which one they got:

1. **Claims** — name, ``preferred_username``/``upn``, ``oid``, ``tid``, and any
   ``groups``/``roles`` the tenant chose to emit. Free, offline, no extra
   permission, available the moment a token arrives.
2. **Microsoft Graph ``/me``** — job title, department, office, phone… Needs a
   *Graph* token, which the inbound token is not. Two ways to get one:
   * **OBO** (``GRAPH_OBO_PROVIDER_NAME``) — AgentCore Identity exchanges the
     inbound user token for a downstream Graph token (RFC 8693). The agent never
     handles a client secret; the exchange happens in the token vault. This is
     the production path and needs an OAuth2 credential provider configured in
     AgentCore Identity for the Entra tenant.
   * **Relay** — the platform proxy forwards the Graph token it already holds
     (the SPA sends it as the platform's own bearer) in
     ``X-Amzn-Bedrock-AgentCore-Runtime-Custom-Graph-Token``. No AWS-side setup,
     which is what makes the demo work in an account with no credential provider,
     and it is off by default on the proxy (``AGENT_TOKEN_RELAY``).

Environment (all optional — every one of them missing is a reported degradation,
never a crash):
  ENTRA_TENANT_ID          tenant to pin ``tid`` and the JWKS/issuer against
  ENTRA_ALLOWED_AUDIENCE   expected ``aud`` (the SPA client id for an ID token)
  GRAPH_OBO_PROVIDER_NAME  AgentCore Identity OAuth2 credential provider to
                           exchange the inbound token with
  GRAPH_OBO_SCOPES         comma-separated, default ``User.Read``
"""

import hashlib
import os
import ssl
import time
from contextvars import ContextVar

import certifi
import httpx
import jwt
from opentelemetry import trace

tracer = trace.get_tracer("whoami-strands")

LOGIN_BASE = "https://login.microsoftonline.com"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# A Microsoft Graph access token carries one of these as its `aud`.
GRAPH_AUDIENCES = {"https://graph.microsoft.com", "00000003-0000-0000-c000-000000000000"}

# Custom headers the platform proxy may relay. The
# `X-Amzn-Bedrock-AgentCore-Runtime-Custom-` prefix is not decoration: it is the
# ONLY `x-amzn-` prefix AgentCore forwards to agent code (see the SDK's
# `is_forwardable_header`), so anything else would be dropped in transit.
ID_TOKEN_HEADER = "x-amzn-bedrock-agentcore-runtime-custom-id-token"
GRAPH_TOKEN_HEADER = "x-amzn-bedrock-agentcore-runtime-custom-graph-token"

CLOCK_SKEW_LEEWAY = 60  # seconds
HTTP_TIMEOUT = 10

# Claims we surface as "person information". Everything else in the token is
# protocol machinery (nonce, at_hash, ver, iat…) and only clutters the answer.
PERSON_CLAIMS = (
    "name",
    "given_name",
    "family_name",
    "preferred_username",
    "upn",
    "email",
    "oid",
    "sub",
    "tid",
    "roles",
    "groups",
    "wids",
    "scp",
)

# /me properties that a delegated `User.Read` token can read. Kept to that set on
# purpose: Graph rejects the WHOLE $select when one property needs a permission
# the token does not carry, so an over-eager select loses the profile entirely.
GRAPH_SELECT = (
    "id,displayName,givenName,surname,userPrincipalName,mail,jobTitle,department,"
    "officeLocation,mobilePhone,businessPhones,preferredLanguage,companyName"
)


# --- request-scoped headers --------------------------------------------------
# Set once per run by the entrypoint (agent.py), read by the tools. A ContextVar
# rather than a global because one long-lived runtime serves many concurrent
# invocations, and `asyncio.to_thread` — which is how Strands executes a sync
# tool (strands/tools/decorator.py) — copies the calling context into the worker
# thread, so the tools see the right request's headers and no other's.
_request_headers: ContextVar[dict] = ContextVar("whoami_request_headers", default={})


def remember_request_headers(headers: dict | None) -> None:
    """Record this run's inbound headers. Keys are lower-cased once, here, so no
    caller has to care whether the wire used HTTP/1.1 or HTTP/2 casing."""
    _request_headers.set({str(k).lower(): v for k, v in (headers or {}).items()})


def _headers() -> dict:
    """This run's headers, falling back to the SDK's own context.

    The fallback matters when the entrypoint could not pass them (a different
    host wiring, a local `python agent.py` run): the AgentCore SDK sets the same
    headers on `BedrockAgentCoreContext` before the handler is called.
    """
    headers = _request_headers.get()
    if headers:
        return headers
    try:
        from bedrock_agentcore.runtime import BedrockAgentCoreContext

        sdk_headers = BedrockAgentCoreContext.get_request_headers() or {}
    except Exception:  # pragma: no cover - SDK shape changed / not on AgentCore
        return {}
    return {str(k).lower(): v for k, v in sdk_headers.items()}


def _bearer(value: str) -> str:
    value = (value or "").strip()
    if value.lower().startswith("bearer "):
        return value.split(" ", 1)[1].strip()
    return value


def fingerprint(token: str) -> str:
    """A stable, non-reversible handle for a token, for logs, spans and answers.

    The token itself must never reach the model, a span attribute or a log line;
    this is what goes in its place when two answers need to be told apart.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12] if token else ""


def caller_token() -> tuple[str | None, str]:
    """The caller's Entra token and how it reached us.

    Sources, in order: an `Authorization` bearer, then the platform proxy's
    relay. Which one arrives is a property of the runtime's header allowlist
    (see the module docstring), so both are checked and neither is assumed.
    `AWS4-…` in `Authorization` is the SigV4 signature of an IAM-authorized
    invoke, never a user token — treating it as one would be how a caller's
    *absence* of identity turns into a confusing parse error.
    """
    headers = _headers()
    raw = headers.get("authorization", "")
    if raw and not raw.upper().startswith("AWS4-"):
        token = _bearer(raw)
        if token:
            return token, "jwt-inbound"
    relayed = _bearer(headers.get(ID_TOKEN_HEADER, ""))
    if relayed:
        return relayed, "relayed-by-platform"
    return None, "none"


# --- token inspection --------------------------------------------------------
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _jwks_client(tenant: str) -> jwt.PyJWKClient:
    """One JWKS client per tenant, kept for the life of the runtime.

    PyJWKClient caches the fetched keys, so this is what stops every tool call
    from re-downloading the tenant's signing keys.

    The explicit certifi trust store is not belt-and-braces: PyJWKClient fetches
    with `urllib.request`, which trusts the *system* store, and on a developer Mac
    that store is empty for Python — every verification then fails with
    CERTIFICATE_VERIFY_FAILED and gets reported as "token rejected", which reads
    as an auth problem and is not one. certifi is already in the zip (httpx
    depends on it), so pinning it here costs nothing and makes local and runtime
    behave the same.
    """
    client = _jwks_clients.get(tenant)
    if client is None:
        client = jwt.PyJWKClient(
            f"{LOGIN_BASE}/{tenant}/discovery/v2.0/keys",
            cache_keys=True,
            timeout=HTTP_TIMEOUT,
            ssl_context=ssl.create_default_context(cafile=certifi.where()),
        )
        _jwks_clients[tenant] = client
    return client


def _tenant_id() -> str:
    return os.environ.get("ENTRA_TENANT_ID", "").strip()


def _allowed_audience() -> str:
    return os.environ.get("ENTRA_ALLOWED_AUDIENCE", "").strip()


def is_graph_token(claims: dict) -> bool:
    return claims.get("aud") in GRAPH_AUDIENCES


def inspect_token(token: str) -> dict:
    """Decode a token and say exactly how much of it we were able to verify.

    Returns ``{"claims", "header", "verification"}``. Never raises for a bad
    token — an unreadable or rejected token is an *answer* here ("this is what
    arrived and this is why it is not trusted"), not an exception, because the
    whole point of the agent is to explain the auth path it is sitting in.
    """
    result = {
        "claims": {},
        "header": {},
        "verification": {
            "signature_verified": False,
            "method": "none",
            "detail": "",
            "tenant_pinned": False,
            "audience_pinned": False,
            "tenant_mismatch": False,
        },
    }
    try:
        result["header"] = jwt.get_unverified_header(token)
        result["claims"] = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as error:
        result["verification"]["detail"] = f"token is not a readable JWT: {error}"
        return result

    claims = result["claims"]
    verification = result["verification"]
    tenant = _tenant_id()
    audience = _allowed_audience()

    if is_graph_token(claims):
        # Documented in app/auth.py and true here too: a Graph access token is a
        # first-party resource token (its header carries a `nonce`) that nobody
        # but Graph can validate. Saying "signature not verified" and pointing at
        # the /me call is honest; pretending JWKS could check it would not be.
        verification["method"] = "graph-me"
        verification["detail"] = (
            "Microsoft Graph access token — not verifiable against the tenant JWKS by design; "
            "the live Graph /me call is the authoritative check"
        )
    elif not tenant:
        verification["detail"] = "ENTRA_TENANT_ID is not set on this runtime, so nothing could be pinned"
    else:
        verification["tenant_pinned"] = True
        options = {"verify_aud": bool(audience)}
        try:
            signing_key = _jwks_client(tenant).get_signing_key_from_jwt(token).key
            verified_claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                issuer=f"{LOGIN_BASE}/{tenant}/v2.0",
                audience=audience or None,
                leeway=CLOCK_SKEW_LEEWAY,
                options=options,
            )
            result["claims"] = verified_claims
            claims = verified_claims
            verification.update(
                signature_verified=True,
                method="tenant-jwks",
                audience_pinned=bool(audience),
                detail="RS256 signature, issuer, expiry" + (" and audience" if audience else ""),
            )
        except jwt.PyJWTError as error:
            verification["method"] = "tenant-jwks"
            verification["detail"] = f"rejected by local verification: {error}"

    # The tenant pin is a claim check, not a signature check, so it is reported
    # separately — and it overrides everything: a perfectly valid signature from
    # the WRONG tenant is exactly the cross-tenant case the platform boundary
    # refuses, and "AgentCore let it through" must not be able to rescue it.
    if tenant and claims.get("tid") and claims.get("tid") != tenant:
        verification["signature_verified"] = False
        verification["tenant_mismatch"] = True
        verification["detail"] = (
            f"token was issued by tenant {claims.get('tid')}, this runtime is pinned to {tenant}"
        )
    return result


def person_claims(claims: dict) -> dict:
    """The identity-bearing subset of a token, in a fixed order."""
    return {name: claims[name] for name in PERSON_CLAIMS if name in claims and claims[name] not in ("", None)}


def token_lifetime(claims: dict) -> dict:
    now = int(time.time())
    exp = claims.get("exp")
    info: dict = {"expired": None, "expires_in_seconds": None}
    if isinstance(exp, (int, float)):
        info["expired"] = now > int(exp) + CLOCK_SKEW_LEEWAY
        info["expires_in_seconds"] = int(exp) - now
    return info


# --- Microsoft Graph ---------------------------------------------------------
def _obo_scopes() -> list[str]:
    raw = os.environ.get("GRAPH_OBO_SCOPES", "User.Read")
    return [scope.strip() for scope in raw.split(",") if scope.strip()]


def _obo_graph_token(provider_name: str) -> str:
    """Exchange the inbound user token for a Graph token via AgentCore Identity.

    ``ON_BEHALF_OF_TOKEN_EXCHANGE`` is an RFC 8693 exchange run by the Identity
    service: it takes the workload access token AgentCore minted for *this user's*
    request (the ``WorkloadAccessToken`` header, which only exists when the runtime
    has JWT inbound auth) and returns a downstream token for the configured
    provider. The client secret lives in the token vault, never in this zip.

    The decorator injects the token as a keyword argument, which is why this
    otherwise pointless inner function exists — it is the smallest thing that can
    receive it.
    """
    from bedrock_agentcore.identity.auth import requires_access_token

    @requires_access_token(
        provider_name=provider_name,
        scopes=_obo_scopes(),
        auth_flow="ON_BEHALF_OF_TOKEN_EXCHANGE",
    )
    def _take(*, access_token: str) -> str:
        return access_token

    return _take()


def graph_access_token() -> tuple[str | None, str, str]:
    """A token that can call Microsoft Graph — ``(token, source, detail)``.

    Order is deliberate: OBO first because it is the path with no relayed
    credential, relay second because it is the one that works with no AWS-side
    setup, and the inbound token last for the case where it is *already* a Graph
    token (the platform's own bearer, relayed as-is).
    """
    provider = os.environ.get("GRAPH_OBO_PROVIDER_NAME", "").strip()
    if provider:
        with tracer.start_as_current_span("identity.obo_exchange") as span:
            span.set_attribute("auth.obo.provider", provider)
            try:
                token = _obo_graph_token(provider)
                span.set_attribute("auth.obo.ok", True)
                return token, "agentcore-identity-obo", f"exchanged via credential provider {provider}"
            except Exception as error:  # noqa: BLE001 - reported, never fatal
                span.set_attribute("auth.obo.ok", False)
                span.set_attribute("auth.obo.error", type(error).__name__)
                obo_detail = f"OBO exchange failed ({type(error).__name__}: {error})"
    else:
        obo_detail = "GRAPH_OBO_PROVIDER_NAME is not set on this runtime"

    relayed = _bearer(_headers().get(GRAPH_TOKEN_HEADER, ""))
    if relayed:
        return relayed, "relayed-by-platform", f"{obo_detail}; used the token relayed by the backend proxy"

    token, source = caller_token()
    if token:
        claims = jwt.decode(token, options={"verify_signature": False}) if _readable(token) else {}
        if is_graph_token(claims):
            return token, f"inbound-token ({source})", "the inbound token is itself a Microsoft Graph token"
    return None, "unavailable", obo_detail


def _readable(token: str) -> bool:
    try:
        jwt.get_unverified_header(token)
        return True
    except jwt.PyJWTError:
        return False


def graph_me(token: str) -> tuple[dict | None, str]:
    """``GET /me`` — the person behind the token. ``(profile, detail)``.

    Falls back to an unfiltered ``/me`` when the $select is refused, because a
    single property the token may not read would otherwise cost the whole
    profile — and the default projection is always readable with ``User.Read``.
    """
    with tracer.start_as_current_span("graph.me") as span:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT) as client:
                response = client.get(f"{GRAPH_BASE}/me?$select={GRAPH_SELECT}", headers=headers)
                if response.status_code == 400:
                    span.set_attribute("graph.select_rejected", True)
                    response = client.get(f"{GRAPH_BASE}/me", headers=headers)
        except httpx.HTTPError as error:
            span.set_attribute("graph.ok", False)
            return None, f"Graph request failed: {type(error).__name__}: {error}"

        span.set_attribute("graph.status_code", response.status_code)
        if response.status_code != 200:
            span.set_attribute("graph.ok", False)
            return None, f"Graph /me returned {response.status_code}: {response.text[:200]}"
        span.set_attribute("graph.ok", True)
        profile = {key: value for key, value in response.json().items() if not key.startswith("@")}
        return profile, "Microsoft Graph /me"


# --- the one call the tools make ---------------------------------------------
def resolve_identity(*, with_profile: bool) -> dict:
    """Everything known about the caller, as one plain dict.

    One function so that "what did the agent actually see?" has exactly one
    answer, whichever tool asked. Span attributes carry the *shape* of the
    result — never the token, never the person's name or mail: `enduser.id` is
    the opaque directory object id, which is what a trace needs to correlate
    runs without turning CloudWatch into a copy of the directory.
    """
    with tracer.start_as_current_span("identity.resolve") as span:
        token, source = caller_token()
        span.set_attribute("auth.token_source", source)
        result: dict = {
            "authenticated": False,
            "token_source": source,
            "token_fingerprint": fingerprint(token or ""),
            "identity": {},
            "verification": {},
            "profile": None,
            "profile_source": "not requested",
            "notes": [],
        }
        if not token:
            result["notes"].append(
                "No caller token reached this runtime. Either this runtime does not allowlist the header "
                "that carries it (requestHeaderAllowlist — AgentCore drops every header the runtime does "
                "not ask for, including Authorization), or the backend proxy is not relaying it "
                "(AGENT_TOKEN_RELAY=1). With SSO off (AUTH_MODE=iam) there is no user token to send at all."
            )
            span.set_attribute("auth.authenticated", False)
            return result

        inspected = inspect_token(token)
        claims = inspected["claims"]
        identity = person_claims(claims)
        verification = inspected["verification"]
        # Under JWT inbound auth the token got past AgentCore's authorizer to be
        # here at all — signature, issuer and audience against the tenant's
        # discovery document. That is a real proof and worth recording as one, but
        # it is not a substitute for the local check: the same code runs behind
        # SigV4, where nothing validated anything.
        verification["validated_upstream"] = source == "jwt-inbound"
        result["identity"] = identity
        result["verification"] = verification
        result["token"] = {
            "issuer": claims.get("iss", ""),
            "audience": claims.get("aud", ""),
            "algorithm": inspected["header"].get("alg", ""),
            "kind": "graph-access-token" if is_graph_token(claims) else "oidc-token",
            **token_lifetime(claims),
        }
        # Fail closed: claims alone never make a caller authenticated. Something
        # has to have checked them — our JWKS verification, or AgentCore's
        # authorizer — and an expired or wrong-tenant token is never accepted by
        # either. Anything short of that is reported as identity we can read but
        # cannot vouch for, which is exactly what an unverified token is.
        result["authenticated"] = bool(
            identity
            and not result["token"].get("expired")
            and not verification["tenant_mismatch"]
            and (verification["signature_verified"] or verification["validated_upstream"])
        )
        if identity and not result["authenticated"]:
            result["notes"].append(
                "The token was readable but not verified here"
                + (f": {verification['detail']}" if verification["detail"] else "")
                + " — treat these claims as unconfirmed."
            )

        span.set_attribute("auth.authenticated", result["authenticated"])
        span.set_attribute("auth.signature_verified", bool(inspected["verification"]["signature_verified"]))
        if claims.get("oid"):
            span.set_attribute("enduser.id", str(claims["oid"]))
        if claims.get("tid"):
            span.set_attribute("enduser.tenant", str(claims["tid"]))

        if with_profile:
            graph_token, graph_source, graph_detail = graph_access_token()
            result["profile_source"] = graph_source
            span.set_attribute("auth.graph_token_source", graph_source)
            if graph_token is None:
                result["notes"].append(
                    "No Microsoft Graph token available, so the answer is limited to the token's own claims. "
                    + graph_detail
                )
            else:
                profile, detail = graph_me(graph_token)
                result["profile"] = profile
                result["notes"].append(detail if profile else f"Graph lookup failed: {detail}")
                if profile is None:
                    result["profile_source"] = f"{graph_source} (failed)"
        return result


def runtime_auth_facts() -> dict:
    """What this runtime is configured for — no secrets, header NAMES only.

    Deliberately reports presence rather than values: `AGENT_TOKEN_RELAY=1` is a
    fact worth showing an operator, the token it relays is not.
    """
    headers = _headers()
    trace_id = trace.get_current_span().get_span_context().trace_id
    return {
        "headers_received": sorted(headers.keys()),
        "inbound_auth_seen": caller_token()[1],
        "entra_tenant_pinned": bool(_tenant_id()),
        "entra_audience_pinned": bool(_allowed_audience()),
        "obo_provider_configured": bool(os.environ.get("GRAPH_OBO_PROVIDER_NAME", "").strip()),
        "obo_scopes": _obo_scopes(),
        "graph_token_relayed": GRAPH_TOKEN_HEADER in headers,
        "id_token_relayed": ID_TOKEN_HEADER in headers,
        "otel_enabled": os.environ.get("OTEL_SDK_DISABLED", "").strip().lower() not in ("1", "true", "yes", "on"),
        "otel_trace_id": f"{trace_id:032x}" if trace_id else "",
    }
