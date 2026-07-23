# AGENTS.md

Canonical engineering guide for this repository — the cross-tool standard file
(read by Claude Code and other agentic tools). `CLAUDE.md` imports this file;
other tools read `.agents/rules/` and run `.agents/workflows/`. Keep this file
as the single source of truth — do not duplicate its content elsewhere; point
to it.

## What this is

Phase 0 is a validation spike for an SDLC agent platform: a **local Next.js
16 / React 19 / CopilotKit v2 (subpath APIs) + A2UI frontend**
(`Phase0/frontend`) and a **local FastAPI backend-for-frontend proxy**
(`Phase0/backend`) that streams **AG-UI over SSE** to **Strands / LangGraph
agents running remotely on Amazon Bedrock AgentCore**. The backend and frontend
live once, in `Phase0/`; `cloud_deploy/` supplies their enterprise env and holds
the one deliberate fork — the agents — see invariants 4 and 7. Deep background: `Phase0/README.md` and
`Phase0/ARCHITECTURE.md`.

## Architecture invariants (do not break)

1. **The backend is a thin proxy.** `Phase0/backend/app/agui_proxy.py`
   SigV4-signs every AgentCore call and pipes the AG-UI SSE stream back
   **unbuffered**. Never buffer it.
2. **The agent catalog is DB-backed and AgentCore-synced. No agent id/ARN in
   env.** Agents are discovered from the AgentCore control plane
   (`Phase0/backend/app/agents_catalog.py`, `catalog_service.py`) and upserted
   into the platform DB; the proxy routes on the DB entry's `runtime_arn`. The
   app is **fully generic** — there is no per-agent backend or frontend code.
3. **Two independent auth layers.** Layer A (browser ↔ backend) is controlled
   by `AUTH_MODE` (`iam` or `entra`): in `entra` mode, identity comes from the
   Entra/Graph access token and roles are derived from AD-group membership
   **server-side** (`app/auth.py`) — never trust the client. Layer B (backend ↔
   AgentCore) is whatever the **target runtime** accepts, read from the catalog's
   AgentCore-synced `inbound_auth` and never from a global setting: **SigV4** for
   an IAM-authorized runtime (the default — the agent never learns who asked), or
   the **caller's own Entra token** forwarded as the bearer for a JWT-authorized
   one, which AgentCore validates against the tenant's OIDC discovery document
   before the agent runs. The two layers stay independent, and a JWT agent is not
   a way around Layer A — every route still goes through
   `require_platform_access`. See `Phase0/docs/IDENTITY-AWARE-AGENTS.md`.
4. **Agents deploy to AgentCore as direct-code zips, and the LLM provider is
   forked, not configured.** Each environment has exactly one provider, so the
   choice is made by *which copy you are in*, never at runtime:
   - `Phase0/agents/<a>/model_factory.py` — **Amazon Bedrock only.** No gateway
     code path exists; setting `BEDROCK_ENDPOINT_URL` here does nothing.
   - `cloud_deploy/agents/<a>/model_factory.py` — **GenAI marketplace gateway
     only** (`x-api-key`). No Bedrock code path exists; the endpoint and key are
     mandatory and it refuses to build without them.

   The enterprise account has no Bedrock model access, and the previous
   env-driven switch meant one missing variable silently sent enterprise traffic
   to Amazon Bedrock. The fork makes that unreachable rather than merely
   discouraged. **`model_factory.py` is the ONLY file allowed to differ between
   the two copies** — an agent change (prompt, tools, graph, requirements) must
   land in both. Run `cloud_deploy/scripts/sync_agents.sh` to propagate, and
   `cloud_deploy/scripts/check_agent_sync.sh` to prove no drift and that neither
   side grew the other's provider. Never hardcode a model id.
5. **Generative UI is A2UI, rendered generically** through the rich catalog
   (`Phase0/frontend/src/components/a2ui/richCatalog.tsx`). Adding a UI
   capability means extending that catalog — never adding per-agent React
   cards.
6. **The frontend is a modified Next.js 16.** Per
   `Phase0/frontend/AGENTS.md`, read `node_modules/next/dist/docs/` before
   writing any Next.js code — APIs and conventions may differ from training
   data.
7. **`cloud_deploy/` is the enterprise side: env + the agent fork.** The
   backend and frontend live once, in `Phase0/` — `cloud_deploy/` never forks
   them and only supplies their enterprise env files (Entra client id,
   per-component `.env`s). The **agents are the one deliberate exception**
   (invariant 4): `cloud_deploy/agents/<a>/` is a permanent second copy whose
   `model_factory.py` is gateway-only. Everything else in that copy is kept
   byte-identical to `Phase0/agents/<a>/` by the sync + gate scripts. The
   enterprise delivery in `win_deployed/` therefore packages **backend/frontend
   from `Phase0/` and agents from `cloud_deploy/`**. See
   `cloud_deploy/README.md`.

## Commands

```bash
# Backend
cd Phase0/backend
uv venv .venv -p 3.13 && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000

# Frontend
cd Phase0/frontend
npm install && npm run dev          # http://localhost:3000

# Build an agent zip (direct-code deployment)
cd Phase0
./scripts/build_zip.sh agents/<agent-dir>     # -> Phase0/build/<agent>.zip

# Deploy an agent
cd Phase0
uv run scripts/deploy_agent.py <agent-name> <zip-path>

# Change runtime config only (header allowlist, authorizer, env) — keeps the
# code the runtime already serves, so no build and no 37-51 MB upload
uv run scripts/deploy_agent.py <agent-name> --config-only

# Smoke (backend must be running; hits live AgentCore)
cd Phase0
uv run scripts/smoke_test.py                  # respects BACKEND_URL, default http://localhost:8000

# Lint / verify Python
cd Phase0
ruff check agents backend/app --exclude '**/.venv/**'

# Frontend verify
cd Phase0/frontend
npm run build && npm run lint

# Run an agent standalone for debugging (the backend CANNOT be pointed at it —
# the proxy always resolves runtime_arn from the catalog and SigV4s to AgentCore;
# LOCAL_AGENT_URL_* no longer exists). Post to /invocations directly instead.
cd Phase0/agents/<agent-dir> && python agent.py     # serves :8080, GET /ping
```

Agents live in **two copies** (invariant 4): `Phase0/agents/<name>/` (Bedrock)
and `cloud_deploy/agents/<name>/` (gateway). Both hold `sdlc-planner-strands`,
`release-readiness-langgraph`, `bug-report-strands`, `a2ui-demo-strands`,
`press-release-strands`, `jira-story-strands`, `whoami-strands`. Each is an
independent AgentCore zip (its own
`requirements.txt` + sources at the zip root) with its own copy of
`model_factory.py` — keep those identical *within* a copy when you edit one.

**Every agent change must land in both copies:**

```bash
# after editing requirements.txt (skip otherwise) — regenerate the pinned resolution
./Phase0/scripts/lock_agents.sh              # -> requirements.lock, REVIEW the diff

# after editing anything under Phase0/agents/
./cloud_deploy/scripts/sync_agents.sh        # copies all but model_factory.py
./cloud_deploy/scripts/check_agent_sync.sh   # gate: no drift, no provider bleed
```

Each agent carries a **`requirements.lock`** — the full pinned resolution (54
packages, vs the 6-8 direct ones in `requirements.txt`). `build_zip.sh` installs
from it and **refuses to build without it**, or if it is older than
`requirements.txt`. Unpinned transitive dependencies silently changed the
delivered bytes twice, so the lock is what makes a dependency bump a reviewable
diff instead of a surprise found by comparing zips.

## Observability

AgentCore ships stdout logs and platform metrics for free. **Traces are opt-in,
and they come from ADOT** — two pieces that must stay in step or the runtime does
not start at all: `aws-opentelemetry-distro` in every agent's `requirements.txt`,
and the `["opentelemetry-instrument", "agent.py"]` entry point in
`Phase0/scripts/deploy_agent.py`. Deploying a zip built before that dependency
landed fails as an initialization timeout, not as a missing-package error.

The account-side prerequisites (CloudWatch Transaction Search;
`logs:PutResourcePolicy` on the execution role) and which stream carries what are
in `cloud_deploy/README.md` under "Logs and traces".

## Where things live

- **Backend routing / catalog:** `Phase0/backend/app/agents_catalog.py`,
  `catalog_service.py` (DB upsert from AgentCore), `agui_proxy.py` (SigV4 +
  SSE pipe), `auth.py` (Layer A), `admin.py` (catalog admin screen, `/admin`,
  gated to the `admin` role).
- **Add a UI capability:** extend
  `Phase0/frontend/src/components/a2ui/richCatalog.tsx` (see the
  `add-a2ui-component` workflow) — never add per-agent frontend code.
- **Add an agent:** scaffold under `Phase0/agents/<name>/` (see the
  `new-agent` workflow), then add it to `AGENT_DIRS` in
  `cloud_deploy/scripts/_agents.sh` and run `sync_agents.sh` so the enterprise
  copy exists too — the catalog picks it up automatically on the next AgentCore
  sync; there is no frontend or backend code to write per agent.
- **Give an agent the caller's identity:** deploy its runtime with JWT inbound
  auth (`scripts/deploy_agent.py --auth=jwt`, defaults per `JWT_AUTH_AGENTS`) and
  read the token in the agent — reference implementation
  `Phase0/agents/whoami-strands/`, full write-up in
  `Phase0/docs/IDENTITY-AWARE-AGENTS.md`. There is no backend or frontend code to
  add per agent: the proxy signs on the catalog's `inbound_auth`.
- **Change the LLM provider:** `Phase0/agents/*/model_factory.py` (Bedrock) or
  `cloud_deploy/agents/*/model_factory.py` (gateway) — never both in one edit,
  and never add the other's provider to either (the gate rejects it).
- **AWS facts and setup:** `.agents/rules/40-aws.md`, `Phase0/aws-setup/`.

## Verify

Before considering a change complete:

- `cd Phase0 && ruff check agents backend/app --exclude '**/.venv/**'` — clean.
- `ruff check cloud_deploy/agents` — clean (the enterprise agent fork).
- `./cloud_deploy/scripts/check_agent_sync.sh` — OK. Required after **any**
  agent change: it is what keeps the two copies one product, and what proves
  neither side can reach the other's LLM provider.
- `cd Phase0/frontend && npm run build && npm run lint` — green.

`scripts/smoke_test.py` needs a running backend and real AWS credentials
against live AgentCore runtimes, so it cannot run headless as part of routine
verification — run it manually when you need to confirm end-to-end behavior.
See `.agents/rules/20-verify.md`.

## Collaboration protocol — PR-based, every change

`git pull` on `main` first → create a new branch off `main` → commit → push
the branch → open a PR → merge the PR → `git pull` `main`. Never commit
directly to `main`; never force-push `main`. On push rejection,
`git pull --rebase`. See `.agents/rules/50-collaboration.md`.

**Branches are permanent — never delete one.** Merging does not retire a
branch; it stays after the merge, local and remote. Merge with plain
`gh pr merge` — never `--delete-branch`/`-d`, `git branch -d`/`-D`,
`git push origin --delete`, or `/clean_gone`. `main` keeps the result of a
change; only the branch keeps the work that produced it.

## Tool-specific setup

- **Claude Code:** `CLAUDE.md` (imports this file), `.claude/agents/`
  subagents (`phase0-verifier`, `a2ui-component-builder`,
  `agentcore-agent-builder`), `.claude/commands/` (`/check`, `/run`,
  `/build`, `/verify`, `/smoke`, `/deploy`, `/add-a2ui-component`,
  `/new-agent`, `/aws-bootstrap`), `.claude/launch.json` (dev server),
  `.claude/settings.json` (permissions).
- **Other agentic tools:** this `AGENTS.md`, always-on rules in
  `.agents/rules/`, and slash workflows in `.agents/workflows/` (same names as
  the Claude Code commands above).
