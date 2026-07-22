# Identity-aware agents — JWT inbound auth, OBO, and the person behind the token

How an agent on AgentCore learns **who is asking**, using the same Entra ID
sign-in the platform already has. Reference implementation:
`Phase0/agents/whoami-strands/`.

Everything else in Phase 0 is deliberately identity-blind: the backend proxy
SigV4-signs every AgentCore call as the trusted caller, and the user's identity
stops at the platform boundary (AGENTS.md invariant 3, Layer A / Layer B). This
document covers the one agent that is not, and the plumbing that makes it work
without changing the other six.

## The shape of it

```
browser (MSAL)                backend proxy                 AgentCore                agent
   │                              │                             │                      │
   │ Authorization: Bearer <Graph token> ──► require_platform_access (Layer A)          │
   │ X-Agent-Authorization: Bearer <ID token>                    │                      │
   │                              │                             │                      │
   │                     catalog.inbound_auth?                   │                      │
   │                        ├─ iam  ─► SigV4 ───────────────────►│ (no identity)        │
   │                        └─ jwt  ─► Authorization: Bearer ───►│ validates the JWT ──►│ claims
   │                                   (the ID token)            │ against the tenant   │
   │                                                             │ discovery document   │
```

Two tokens leave the browser, and that is not an accident. The platform's own
bearer is a **Microsoft Graph access token** — the backend calls Graph `/me` with
it to resolve identity and AD-group roles (`app/auth.py`). No OIDC authorizer can
validate that token: it is a first-party resource token whose header carries a
`nonce`, and only Graph can check it. So for AgentCore the browser sends a
second, tenant-issued token in `X-Agent-Authorization` — by default the Entra
**ID token**, which MSAL already returns with every silent acquisition, whose
`aud` is the SPA client id and whose issuer is the tenant's v2.0 endpoint.

## Which runtime gets JWT auth

Per agent, at deploy time — never globally:

```bash
cd Phase0
./scripts/build_zip.sh agents/whoami-strands
uv run scripts/deploy_agent.py whoami-strands build/whoami-strands.zip   # --auth=jwt by default
```

`JWT_AUTH_AGENTS` in `scripts/deploy_agent.py` holds the defaults; `--auth=iam|jwt`
overrides per deploy. The authorizer is derived from values `.env` already has:

| Setting | Default | Meaning |
| --- | --- | --- |
| `ENTRA_DISCOVERY_URL` | derived from `ENTRA_TENANT_ID` | OIDC discovery document AgentCore validates against |
| `ENTRA_ALLOWED_AUDIENCE` | `ENTRA_SPA_CLIENT_ID` | expected `aud` — the SPA client id, because the default token is an ID token |
| `ENTRA_ALLOWED_CLIENTS` | – | optional `client_id` allowlist |

A runtime is **either** IAM-authorized **or** JWT-authorized. Calling a
JWT runtime with SigV4 returns `403 ACCESS_DENIED: Authorization method mismatch`,
which is why this had to become a per-agent decision: reading it from `AUTH_MODE`
(what the script used to do) flipped *every* runtime to JWT the moment browser SSO
was switched on, breaking the five agents the proxy still SigV4-signs.

The backend learns which is which from the catalog. `discover_runtimes()` reads
each runtime's `authorizerConfiguration` and stores `inbound_auth` (`iam`/`jwt`)
on the catalog row — AgentCore-sourced and read-only, refreshed on every sync,
shown as a badge in `/admin`. The proxy signs each call on that value. If the
catalog is stale the call is signed the wrong way, so **re-sync after switching a
runtime's auth**; the deploy script prints the runtime's actual inbound auth
after it goes READY for exactly this reason.

## Turning it on

Backend `Phase0/.env`:

```
AUTH_MODE=entra          # Layer A: the platform requires a signed-in user
ENTRA_TENANT_ID=…        # already required by SSO
ENTRA_SPA_CLIENT_ID=…    # already required by SSO; doubles as the JWT audience
AGENT_TOKEN_RELAY=1      # optional, see "Getting a Graph token" below
```

Frontend `Phase0/frontend/.env.local`:

```
NEXT_PUBLIC_AUTH_MODE=entra
NEXT_PUBLIC_ENTRA_AGENT_SCOPES=      # empty = send the ID token (no tenant changes needed)
```

With SSO off (`AUTH_MODE=iam`) there is no user token at all, so a JWT agent
cannot be reached. The proxy says so in as many words — a 401 naming the missing
`X-Agent-Authorization` header — rather than letting AgentCore answer with an
opaque 403.

### Using an API scope instead of the ID token

Set `NEXT_PUBLIC_ENTRA_AGENT_SCOPES=api://<api-client-id>/agent.invoke` and
`ENTRA_ALLOWED_AUDIENCE=api://<api-client-id>`. More orthodox — the token is
minted for this API rather than being the client's own — but it needs an
"Expose an API" scope on the app registration **and** `accessTokenAcceptedVersion: 2`
in that app's manifest. Without the manifest field Entra issues a v1 token whose
issuer is `https://sts.windows.net/<tid>/`, which will never match the v2.0
discovery document, and the rejection says nothing about why.

## Getting the person, not just the claims

The token already carries real person information — `name`, `preferred_username`,
`oid`, `tid`, and whatever `groups`/`roles` the tenant emits. The directory record
(job title, department, office, phone) needs a **Graph** token, which the inbound
token is not. Two ways, and the agent reports which one it used:

### 1. OBO — AgentCore Identity token exchange (the production path)

AgentCore Identity exchanges the caller's inbound token for a downstream Graph
token (RFC 8693). The client secret lives in the token vault; nothing about it
reaches the agent's zip. Requires the runtime to have **JWT inbound auth** — the
exchange is keyed on the `WorkloadAccessToken` AgentCore mints for that user's
request, which only exists when a user token came in.

```bash
aws bedrock-agentcore-control create-oauth2-credential-provider \
  --name entra-graph \
  --credential-provider-vendor MicrosoftOauth2 \
  --oauth2-provider-config-input '{
      "microsoftOauth2ProviderConfig": {
        "tenantId":     "<tenant-id>",
        "clientId":     "<confidential-app-client-id>",
        "clientSecret": "<secret>"
      }}'
```

Then set `GRAPH_OBO_PROVIDER_NAME=entra-graph` (and optionally
`GRAPH_OBO_SCOPES=User.Read`) in `Phase0/.env` and redeploy — `deploy_agent.py`
passes both onto the runtime. Note the client id must belong to a **confidential**
app registration: a SPA cannot hold a secret, so this is usually a second
registration, with the SPA's tokens accepted as the exchange input.

### 2. Relay — the token the platform already holds

`AGENT_TOKEN_RELAY=1` makes the proxy forward the caller's tokens to the runtime
in AgentCore's custom forwardable headers:

| Header | Carries | Used for |
| --- | --- | --- |
| `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Graph-Token` | the platform's Graph token | Graph `/me` without an OBO provider |
| `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Id-Token` | the tenant-issued token | identity on an **IAM** runtime (local dev, smoke) |

No AWS-side setup, which is what makes the demo work in an account with no
credential provider. Off by default: it hands a delegated user token to the
runtime, and no other agent has any use for one. The
`X-Amzn-Bedrock-AgentCore-Runtime-Custom-` prefix is the only `x-amzn-` prefix
AgentCore forwards to agent code — anything else is dropped in transit.

## How much the agent trusts the token

Under JWT inbound auth AgentCore has already checked signature, issuer and
audience. The agent re-verifies anyway (RS256 against the tenant JWKS, issuer,
audience, expiry, 60s leeway) because the same code also runs behind SigV4, where
nothing checked anything. Its answers carry the verdict, and it is fail-closed:

- claims alone never make a caller authenticated — either local verification
  passed or AgentCore's authorizer did;
- a `tid` that is not the pinned tenant is refused outright, and upstream
  validation cannot rescue it;
- a Graph access token is reported as *not JWKS-verifiable by design*, with the
  live `/me` call named as the authoritative check.

Tokens never reach the model, a log line or a span. What identifies a token in an
answer is a 12-hex SHA-256 prefix.

## OpenTelemetry

Traces come from ADOT and only ADOT: `aws-opentelemetry-distro` in the agent's
`requirements.txt` plus the `["opentelemetry-instrument", "agent.py"]` entry point
in `deploy_agent.py`. On top of the automatic ASGI and model spans this agent adds:

| Span | Attributes |
| --- | --- |
| `tool.whoami` / `tool.my_profile` / `tool.auth_diagnostics` | — |
| `identity.resolve` | `auth.token_source`, `auth.authenticated`, `auth.signature_verified`, `auth.graph_token_source`, `enduser.id`, `enduser.tenant` |
| `identity.obo_exchange` | `auth.obo.provider`, `auth.obo.ok`, `auth.obo.error` |
| `graph.me` | `graph.status_code`, `graph.ok`, `graph.select_rejected` |

`enduser.id` is the directory object id, never the name or mail: enough to
correlate every run by one person, not enough to turn CloudWatch into a copy of
the directory. `auth_diagnostics` returns the current trace id, which is the
quickest way to find a specific run in GenAI Observability.

There is deliberately **no span wrapping the event stream**. Attaching a span
context and detaching it across an async-generator yield is what makes Strands'
own instrumentation crash the SSE stream locally; every span here is short-lived
and synchronous, inside a tool.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `403 ACCESS_DENIED: Authorization method mismatch` | SigV4 sent to a JWT runtime (or the reverse). The catalog's `inbound_auth` disagrees with the runtime — re-sync the catalog. |
| `403 ACCESS_DENIED: OAuth authorization failed: Failed to parse token` | AgentCore's authorizer rejected the bearer. Usually the Graph token was sent instead of the tenant-issued one. |
| `401 Missing Authentication Token` from AgentCore | No `Authorization` header reached the runtime at all. |
| Proxy 401 naming `X-Agent-Authorization` | SSO is off, or the browser could not mint the agent token. |
| Agent says "not verified: Unable to find a signing key" | The token was not signed by the pinned tenant — check `ENTRA_TENANT_ID` on the runtime. |
| Agent says "no Microsoft Graph token available" | Neither `GRAPH_OBO_PROVIDER_NAME` nor `AGENT_TOKEN_RELAY=1` is configured. Identity claims still work. |
| Runtime never goes healthy after a deploy | The usual two: `aws-opentelemetry-distro` missing from the zip, or the container not listening on 8080. |

## What was verified, and what was not

Verified against the live runtime `whoami_strands-cYBywV4ro0` (2026-07-22):
SigV4 is refused with `Authorization method mismatch`; a malformed bearer is
refused by the authorizer, not by the agent; no auth returns 401 — so inbound JWT
validation is genuinely enforced. The catalog syncs `inbound_auth=jwt` for that
runtime and `iam` for the other six; the proxy forwards the bearer for the former
and still SigV4-signs the latter (`a2uidemo` health stayed green). Locally, a
hand-built token drives the full entrypoint → context → tool → claims path, and
JWKS verification really reaches the tenant key endpoint.

**Not verified end to end:** a real Entra ID token from a browser sign-in, and
the OBO exchange — both need an interactive Microsoft login (and, for OBO, a
credential provider with a client secret). Those are the two steps left to a human.
