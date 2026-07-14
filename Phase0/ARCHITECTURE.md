# Phase 0 — Architecture & Data Report

Snapshot of what is actually running as of 2026-07-13. Distinguishes **local**
(your machine) from **remote** (AWS / Microsoft), the structures of each
component, and how they connect. A separate section covers data storage,
because Phase 0 deliberately has **no database yet** — the planned schema (doc
03) is included at the end for context.

AWS account: `122524101917`, region `us-east-1`.

---

## 1. Component inventory — local vs remote

| # | Component | Where | Runs as | Talks to |
|---|---|---|---|---|
| 1 | Next.js frontend + CopilotKit UI | **Local** `:3000` | `npm run dev` | Backend (2), CopilotKit runtime (3), Entra (7) |
| 2 | CopilotKit runtime | **Local** (Next.js API route `/api/copilotkit`) | inside the Next.js process | Backend AG-UI proxy (2b) as `HttpAgent` |
| 3 | FastAPI backend (BFF) | **Local** `:8000` | `uvicorn app.main:app` | AgentCore data plane (4), AgentCore control plane (5), Bedrock (via runtimes), Microsoft Graph (7) |
| 4 | AgentCore Runtimes ×3 | **Remote** AWS | managed microVMs | Bedrock (6) |
| 5 | AgentCore control plane | **Remote** AWS | AWS managed API | — (queried by backend for discovery) |
| 6 | Amazon Bedrock (Claude Haiku 4.5) | **Remote** AWS | AWS managed | — |
| 7 | Microsoft Entra ID + Graph | **Remote** Microsoft | OIDC IdP + directory | issues Graph token to frontend; backend calls Graph /me + checkMemberGroups |
| 8 | S3 deploy bucket | **Remote** AWS | AWS managed | holds agent zips; read by AgentCore at deploy |
| 9 | IAM execution role | **Remote** AWS | AWS managed | assumed by runtimes to call Bedrock/Logs |
| 10 | Thread history store | **Local** browser | `localStorage` | — (no server) |

There is **no EKS, no Temporal, no RDS, no ElastiCache, no Gateway/MCP** in
Phase 0 — those are Phase 1+ per the implementation plan.

---

## 2. The two processes you run locally

### 2a. Frontend (`Phase0/frontend`, port 3000)
- Next.js 16 (App Router) + React 19 + CopilotKit 1.62 (v2 subpath APIs).
- Renders the workspace shell, agent chat, generative-UI cards, the bug canvas,
  and the state inspector.
- Reads config from `Phase0/.env` at startup via `next.config.ts`
  (`NEXT_PUBLIC_*`).
- Contains the **CopilotKit runtime** as an API route
  (`src/app/api/copilotkit/[[...path]]/route.ts`). It registers each agent as an
  `HttpAgent` pointing at the backend's AG-UI proxy — this is the production-style
  `selfManagedAgents` path, never a direct browser→agent connection.

### 2b. Backend (`Phase0/backend`, port 8000)
Backend-for-frontend. Three responsibilities:
- **Catalog & discovery** (`agents_catalog.py`): `GET /api/agents` (static list
  from `.env`) and `GET /api/agentcore/runtimes` (live `list_agent_runtimes`
  against the control plane, enriched with `get_agent_runtime` for protocol).
- **AG-UI proxy** (`agui_proxy.py`): `POST /api/agui/{agent_id}` streams the
  AG-UI SSE request/response between the frontend and the AgentCore runtime.
- **Auth boundary** (`auth.py`): validates the caller (see §4).
- Structured logging (structlog) is wired through `logging_setup.py` and an HTTP
  middleware in `main.py`. `LOG_LEVEL` (default `DEBUG`) sets the level; `LOG_FORMAT`
  is `console` (human-readable) or `json` (one JSON object per line, for CloudWatch).
  structlog runs over the stdlib backend, so third-party libraries render the same
  way and existing `%s`-style call sites keep working.

---

## 3. Request path (one chat message)

```
Browser (CopilotChat)
  → POST /api/copilotkit/agent/{id}/run        (local, CopilotKit runtime)
    → HttpAgent → POST /api/agui/{id}           (local, FastAPI proxy)
      → require_user()  validates identity      (iam: skip / entra: Entra JWT)
      → SigV4-sign the request                   (always, runtimes are IAM-auth)
      → POST https://bedrock-agentcore.us-east-1.amazonaws.com
             /runtimes/{escaped-arn}/invocations?qualifier=DEFAULT   (REMOTE)
        → AgentCore microVM runs agent.py
          → Bedrock Converse (Claude Haiku 4.5)  (REMOTE)
        ← AG-UI SSE event stream (RUN_STARTED, TEXT_*, TOOL_CALL_*, STATE_*, …)
      ← proxy pipes SSE back unchanged
    ← CopilotKit runtime relays to the browser
  ← cards / text / HITL render from the events
```

Every hop is streaming SSE; the proxy does not buffer.

---

## 4. Authentication — two connection modes

Auth has **two independent layers**, which is the key architectural point:

**Layer A — platform boundary (browser ↔ backend).** Controlled by `AUTH_MODE`
(both `AUTH_MODE` on the backend and `NEXT_PUBLIC_AUTH_MODE` on the frontend).
- `AUTH_MODE=iam` (or `off`): no user login; backend serves anyone (local dev).
  The app behaves exactly as before SSO — the escape hatch for local work.
- `AUTH_MODE=entra`: frontend does MSAL sign-in against Entra and acquires a
  **Microsoft Graph access token** (scope `User.Read`), sending it as `Bearer`.
  The backend follows the AI SDLC SSO *method*, hardened:
  1. Local pre-checks pin tenant (`tid`), authorized party (`azp`/`appid` = SPA
     client), audience (= Graph) and enforce `exp`/`nbf` with clock-skew leeway —
     closing the cross-tenant and confused-deputy holes.
  2. **Authoritative** identity: the backend calls Graph `/me` with the token
     (a Graph access token cannot be signature-verified locally; the live call is
     the real check). Cached briefly per token.
  3. **Authorization (RBAC):** `/me/checkMemberGroups` resolves AD-group
     membership → platform roles via `ENTRA_GROUP_ROLE_MAP` + `ENTRA_ADMIN_GROUP_ID`.
     Roles are computed server-side (never trusted from the client) and cached per
     user. Every protected route is **default-deny**; `GET /api/me` reports the
     backend's view of identity + roles, which the SPA mirrors for UI only.
  - `REQUIRED_ROLE` (empty = identity-only) gates use of the AG-UI proxy.

**Layer B — upstream to AgentCore (backend ↔ runtime).** Independent of Layer A.
- The 3 runtimes are deployed with **IAM authorizer**, so the backend **always**
  SigV4-signs the invocation with its AWS credentials — even in entra mode. In
  entra mode the backend has already authenticated the user (Layer A) and now
  acts as the trusted caller (the "backend exchanges the token" pattern, doc 05).

So Entra secures *who may use the platform*; SigV4 secures *the platform calling
AgentCore*. They do not depend on each other.

Entra connection facts (remote):
- Tenant `98c18fba-5be5-4229-a075-90da42d85df3`
- SPA app registration (client) `97ab1446-ac98-4547-aee7-f2042da97aff`
- Backend calls Microsoft Graph (`/me`, `/me/checkMemberGroups`) with the user's
  delegated token; no client secret is stored (all Graph calls are delegated).
- Prerequisites for full RBAC (human, in Entra portal): single-tenant app,
  `User.Read` (add `GroupMember.Read.All`/`Directory.Read.All` if group resolution
  returns empty), and AD security groups whose object ids go in `ENTRA_GROUP_ROLE_MAP`.

### 4.1 Future: per-user agent identity (OBO / 3LO)

Today the agent runtimes use an **IAM authorizer**, so the user's identity stops
at the backend (Layer B is SigV4 only). To let the *agents* act as the signed-in
user, AgentCore supports three OAuth paths (all verified against AWS docs):

- **Inbound JWT authorizer** — redeploy each runtime with
  `authorizerConfiguration.customJWTAuthorizer = {discoveryUrl, allowedClients, allowedAudiences}`
  (Entra ID supported). The backend then forwards the user's Entra access token to
  AgentCore instead of SigV4; AgentCore validates it and the agent runs with the
  user's identity. This is the smallest step from where we are.
- **On-behalf-of (OBO) token exchange** — AgentCore Identity's OAuth Credential
  Provider brokers an RFC 8693 / RFC 7523 §2.1 exchange: it takes the inbound user
  token and mints a downstream token (e.g. for another API) without the agent ever
  handling secrets. Use when the frontend token's audience is our backend, not the
  agent.
- **3LO (authorization-code grant)** — for the agent to call third-party tools
  (Jira, GitHub, Graph) *as the user*, AgentCore Identity's token vault runs the
  user-consent flow; 2LO (client-credentials) covers autonomous access.

None of these are wired yet — they are the roadmap for giving agents a real user
identity beyond the current platform-boundary SSO.

---

## 5. AgentCore runtimes (remote, live)

| Agent id (frontend) | Runtime name | Framework | Protocol | Auth | Version | Status |
|---|---|---|---|---|---|---|
| `planner` | `Planner` | Strands | AGUI | IAM (SigV4) | v3 | READY |
| `release` | `Release_Readiness` | LangGraph | AGUI | IAM (SigV4) | v4 | READY |
| `bugreport` | `bug_report_strands` | Strands | AGUI | IAM (SigV4) | v1 | READY |

- All serve the AgentCore contract: `POST /invocations` (SSE) + `GET /ping` +
  `/ws`, port 8080, linux/arm64.
- Each was deployed as a **zip (direct code deployment)** from
  `s3://agui-demo1-deploy-122524101917/<agent>/deployment_package.zip`.
- Runtime env var `BEDROCK_MODEL_ID=global.anthropic.claude-haiku-4-5-20251001-v1:0`.
- Execution role `agui-demo1-runtime-exec` (Bedrock invoke, CloudWatch Logs,
  X-Ray) — assumed by the runtime, not by you.

---

## 6. Data storage

### 6a. What actually stores data today

| Data | Where it lives | Persistence | Notes |
|---|---|---|---|
| Chat threads (id, agent, title, timestamp) | **Browser `localStorage`** key `phase0-threads` | per-browser, client-only | `src/lib/threads.ts`; capped at 50 |
| Chat messages / run state | **Not persisted** | in-memory during a run | AgentCore session (per session-id) holds state for the LangGraph interrupt; lost after the session |
| Agent catalog (`agent_catalog`) | **Platform DB** (SQLite `phase0.db`, or Postgres via `DATABASE_URL`) | durable | async SQLAlchemy; platform metadata joined to AgentCore runtimes by ARN |
| Admin audit trail (`audit_log`) | **Platform DB** | durable | who/when/what for catalog edits & syncs; actor from Entra identity |
| Deployment artifacts (zips) | **S3** `agui-demo1-deploy-122524101917` | durable | 3 objects |
| Model-access / IAM / runtime config | **AWS account state** | durable | managed by AWS |

The platform DB (async SQLAlchemy) persists **only** the agent catalog and the
admin audit trail. It does **not** store identity, roles, or conversation history:
identity/roles are derived from the Entra ID token per request, and thread history
is intentionally client-side (`localStorage`). Schema is created via
`create_all` for local SQLite and managed by **Alembic** for real (Postgres)
deployments.

### 6b. Planned schema (doc 03, Phase 2–3 — NOT built yet)

When persistence moves server-side (RDS PostgreSQL), the sketch is:

```
agents(id, name, description, protocol[agui|a2a|http], runtime_arn,
       ui_capability, required_roles[], status, owner, created_at)
mcp_servers(id, name, transport, endpoint, gateway_target_id,
            required_roles[], health_status, owner)
skills(id, name, version, s3_uri, manifest_json, status)
agent_skills(agent_id, skill_id, enabled, pinned_version)
threads(id, user_id, agent_id, created_at)
messages(id, thread_id, role, content_json, run_id, created_at)
role_permissions(role, permission)   -- Entra app roles → platform permissions
```

Mapping to today:
- `agents` table is now **implemented** (SQLite via async SQLAlchemy, `phase0.db`;
  swap to Postgres with `DATABASE_URL`). It holds the agent catalog — platform
  metadata (display name, description, **`ui_mode` static|a2ui**, enabled,
  required_role) joined to live AgentCore runtimes by ARN. AgentCore-sourced fields
  (ARN, protocol, status, version) are read-only. The **Admin screen** (`/admin`,
  gated to the `admin` role) edits it; "Sync from AgentCore" auto-registers newly
  discovered **AG-UI** agents with `ui_mode='a2ui'` by default. Note: `ui_mode`
  is retained for forward-compatibility, but the current frontend renders
  **every** agent generatively through the A2UI catalog and does not branch on
  it — there are no per-`ui_mode` code paths left.
- `audit_log` is **implemented** (not in the doc-03 sketch): every admin catalog
  edit and sync is recorded with the acting Entra identity (oid/email), action,
  target and change detail. Operational/request logs are **not** here — those go
  to structlog → stdout → CloudWatch.
- `threads` / `messages` ≈ today's `localStorage` (would move to Postgres, giving
  cross-device history and reopenable threads).
- `role_permissions` ≈ today's `ENTRA_GROUP_ROLE_MAP` env (AD group → role,
  resolved live from Graph) + optional `REQUIRED_ROLE` gate (would become a
  mapping table, with AD-group→role kept in the DB instead of env).
- Temporal gets its own database on the same RDS instance (Phase 3).

---

## 7. Connection & port summary

| From | To | Transport | Auth |
|---|---|---|---|
| Browser | Frontend `:3000` | HTTP | Entra Graph access token (entra mode) |
| Frontend | CopilotKit runtime (same process) | in-process | — |
| CopilotKit runtime | Backend `:8000` `/api/agui/*` | HTTP SSE | forwards `Authorization` header |
| Backend | AgentCore data plane | HTTPS SSE | **SigV4** (always) |
| Backend | AgentCore control plane | HTTPS | SigV4 (discovery) |
| AgentCore runtime | Bedrock | AWS internal | execution role |
| Backend | Microsoft Graph (`/me`, `/me/checkMemberGroups`) | HTTPS | user's delegated token |
| AgentCore | S3 (deploy) | AWS internal | at deploy time |

---

## 8. One-line summary

A **local** Next.js+CopilotKit frontend and a **local** FastAPI backend-for-
frontend proxy three **remote** AG-UI agents running on Amazon Bedrock AgentCore
(Claude Haiku 4.5), with **Entra ID** for platform sign-in and **SigV4** for the
backend→AgentCore hop. **No database yet** — thread history is browser-local; the
Postgres schema above is the Phase 2–3 plan.
