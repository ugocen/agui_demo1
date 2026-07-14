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
agents running remotely on Amazon Bedrock AgentCore**. The app lives once, in
`Phase0/`. `cloud_deploy/` is an enterprise configuration overlay for the same
code — see invariant 7. Deep background: `Phase0/README.md` and
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
   **server-side** (`app/auth.py`) — never trust the client. Layer B (backend
   ↔ AgentCore) is **always SigV4**, independent of Layer A.
4. **Agents deploy to AgentCore as direct-code zips; the model provider is
   env-driven.** Each agent's `model_factory.py`
   (`build_strands_model()` / `build_langchain_model()`) defaults to Amazon
   Bedrock (SigV4) and switches to an enterprise `x-api-key` gateway only when
   both `BEDROCK_ENDPOINT_URL` and `BEDROCK_API_KEY` are set. Never hardcode a
   provider or model id.
5. **Generative UI is A2UI, rendered generically** through the rich catalog
   (`Phase0/frontend/src/components/a2ui/richCatalog.tsx`). Adding a UI
   capability means extending that catalog — never adding per-agent React
   cards.
6. **The frontend is a modified Next.js 16.** Per
   `Phase0/frontend/AGENTS.md`, read `node_modules/next/dist/docs/` before
   writing any Next.js code — APIs and conventions may differ from training
   data.
7. **`cloud_deploy/` is an enterprise config overlay (env only).** The
   application code lives once, in `Phase0/`. `cloud_deploy/` never forks it —
   it only supplies enterprise env files (gateway URL/key, Entra client id,
   per-component `.env`s). See `cloud_deploy/README.md`.

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

# Smoke (backend must be running; hits live AgentCore)
cd Phase0
uv run scripts/smoke_test.py                  # respects BACKEND_URL, default http://localhost:8000

# Lint / verify Python
cd Phase0
ruff check agents backend/app --exclude '**/.venv/**'

# Frontend verify
cd Phase0/frontend
npm run build && npm run lint

# Local agent without AWS (release agent only; no Bedrock needed until the
# final summary) — run the release agent on :8080, then start the backend
# with:
LOCAL_AGENT_URL_RELEASE=http://127.0.0.1:8080/invocations
```

Agents currently live under `Phase0/agents/<name>/`: `sdlc-planner-strands`,
`release-readiness-langgraph`, `bug-report-strands`, `a2ui-demo-strands`,
`press-release-strands`. Each is an independent AgentCore zip (its own
`requirements.txt` + sources at the zip root) with its own copy of
`model_factory.py` — keep the copies identical when you edit one.

## Where things live

- **Backend routing / catalog:** `Phase0/backend/app/agents_catalog.py`,
  `catalog_service.py` (DB upsert from AgentCore), `agui_proxy.py` (SigV4 +
  SSE pipe), `auth.py` (Layer A), `admin.py` (catalog admin screen, `/admin`,
  gated to the `admin` role).
- **Add a UI capability:** extend
  `Phase0/frontend/src/components/a2ui/richCatalog.tsx` (see the
  `add-a2ui-component` workflow) — never add per-agent frontend code.
- **Add an agent:** scaffold under `Phase0/agents/<name>/` (see the
  `new-agent` workflow) — the catalog picks it up automatically on the next
  AgentCore sync; there is no frontend or backend code to write per agent.
- **AWS facts and setup:** `.agents/rules/40-aws.md`, `Phase0/aws-setup/`.

## Verify

Before considering a change complete:

- `cd Phase0 && ruff check agents backend/app --exclude '**/.venv/**'` — clean.
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
