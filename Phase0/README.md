# Phase 0, Validation Spike

Two SDLC-themed AG-UI agents on Amazon Bedrock AgentCore (SDLC Planner on
Strands, Release Readiness on LangGraph), a local FastAPI backend (AG-UI proxy
plus auth), and a local Next.js + CopilotKit frontend that renders agent output
generatively through a **fully-generic A2UI catalog** (no per-agent card
components). Built from `resources/07-phase0-claude-code-plan.md`.

## Layout

```
Phase0/
├── .env                  # config, copied from .env.example, human fills AWS values
├── VERSIONS.md           # pinned dependency versions
├── agents/
│   ├── sdlc-planner-strands/        # Strands agent (S1 stories, S2 estimates, S3 HITL approval)
│   └── release-readiness-langgraph/ # LangGraph agent (S4 checklist+risks+progress, S5 HITL go/no-go)
├── backend/              # FastAPI: /api/agents catalog + /api/agui/{id} SSE proxy
├── frontend/             # Next.js + CopilotKit v2, generic A2UI catalog (Chart/Mermaid/Markdown/Html)
└── scripts/
    ├── build_zip.sh      # ARM64 zip packaging for direct code deployment
    ├── deploy_agent.py   # S3 upload + create/update AgentCore runtime (AGUI protocol)
    └── smoke_test.py     # S1..S5 + auth checks, prints the G0 report
```

## Generative UI — two strategies, picked per agent

An agent's generative UI is rendered one of two ways, chosen per agent by its
catalog `ui_mode` (editable in `/admin`). The difference is **who decides the
layout**:

- **`static`** — the *frontend* does. Hand-authored cards render the agent's tool
  calls: it calls `show_user_stories`, the frontend draws the story cards. Fixed,
  typed, deterministic; the LLM only supplies the data.
- **`a2ui`** — the *agent* does. It is given the A2UI component catalog and emits
  a component tree, which the frontend renders as-is. Free composition; the same
  question can look different twice. Newly discovered agents default to this.

Both are **generic and keyed by tool name, never by agent id** — a card lives in
`frontend/src/components/cards/cardCatalog.tsx` and an A2UI component in
`frontend/src/components/a2ui/richCatalog.tsx`; adding either is a catalog entry,
not per-agent React (invariant 5). Anything neither catalog handles falls to
`useDefaultRenderTool`, which shows a status line so nothing silently disappears.

The modes are **exclusive**: an agent told both "you have `show_user_stories`" and
"you may compose A2UI" picks between them nondeterministically. `static` agents are
therefore left out of the runtime's A2UI list in
`frontend/src/app/api/copilotkit/[[...path]]/route.ts`, so their LLM is never given
the `render_a2ui` tool at all — the client alone cannot enforce this.

**Human-in-the-loop is wired** (`frontend/src/components/hitl/HumanInTheLoop.tsx`)
and is mounted in **both** modes. Those tools are frontend-owned, the run *pauses*
on them, and `bug-report` ships `tools=[]` and cannot function without them — they
are a protocol contract, not a rendering style.

`a2ui-demo` is the canonical `a2ui` agent; `planner` and `release` are the card
agents; `bug-report` and `press-release` are driven entirely by HITL tools.

## Human prerequisites (doc 07 section 2)

**Backend `.env`** (what the FastAPI app reads):

- `AWS_REGION` — used to build AgentCore invocation URLs and to list runtimes
  (model access must be enabled in that region)
- `AUTH_MODE=iam` (Stage A fallback) or `AUTH_MODE=entra` plus the `ENTRA_*` values
- `LOG_LEVEL` (default `DEBUG`), `LOG_FORMAT` (`console` default, or `json` for CloudWatch)
- `DATABASE_URL` (optional; defaults to local SQLite — see "Database")

No runtime ARNs: the proxy routes on the DB catalog (synced from AgentCore),
never on env values (invariant 2).

**Agent deployment is out-of-band** (external CI/CD or manual) and is *not* driven
by the backend. Its config lives with the deploy pipeline, not in the backend `.env`:

- `BEDROCK_MODEL_ID` (model access enabled in the region)
- `DEPLOY_BUCKET` (the deploy step creates it if the credentials allow)
- `EXECUTION_ROLE_ARN` (AgentCore runtime execution role: AgentCore permissions,
  `s3:GetObject` on the bucket, CloudWatch Logs, Bedrock invoke)

If you run `scripts/deploy_agent.py` manually, export those three (plus
`AWS_REGION`) in your shell first — the script requires them from the environment.

- IMPORTANT: local AWS credentials currently resolve to the **root** account.
  Doc 02 Stage A requires a dedicated IAM deployment user, never root. Create
  the deployment user, run `aws configure` (or `aws login`) as that user first.

## Run locally

Agents (only needed for local agent debugging, AgentCore runs them in prod):

```
cd agents/sdlc-planner-strands
uv venv .venv -p 3.13 && uv pip install --python .venv/bin/python -r requirements.txt
BEDROCK_MODEL_ID=... AWS_REGION=... .venv/bin/python agent.py   # port 8080
```

Backend:

```
cd backend
uv venv .venv -p 3.13 && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000
```

Frontend:

```
cd frontend
npm install
npm run dev   # http://localhost:3000
```

An agent can be run standalone on port 8080 (`python agent.py`) for debugging,
but **the backend cannot be pointed at it**: `agui_proxy.py` resolves every target
from the DB catalog entry's AgentCore `runtime_arn` and signs the call per that
entry's `inbound_auth` (SigV4, or the caller's Entra token for a JWT-authorized
runtime — see `docs/IDENTITY-AWARE-AGENTS.md`). The
`LOCAL_AGENT_URL_*` override this README used to describe no longer exists in the
code. To exercise a local agent, post an AG-UI request straight to its
`/invocations`, or check liveness with `curl localhost:8080/ping`.

## Database

The platform DB holds the agent catalog (`agent_catalog`) and an audit trail of
admin mutations (`audit_log`). Identity/roles are **not** stored — they come from
the Entra ID token at request time.

- **Local dev:** defaults to a SQLite file (`backend/phase0.db`), created on
  startup via `Base.metadata.create_all`. No service needed.
- **Real deployments:** set `DATABASE_URL` (e.g.
  `postgresql+asyncpg://user:pass@host:5432/db`) and apply schema with Alembic
  rather than relying on `create_all`:

  ```
  cd backend
  DATABASE_URL=... .venv/bin/alembic upgrade head     # fresh DB → full schema
  # after changing app/models.py:
  DATABASE_URL=... .venv/bin/alembic revision --autogenerate -m "describe change"
  DATABASE_URL=... .venv/bin/alembic upgrade head
  ```

  If a DB already has the tables from `create_all`, baseline it once with
  `alembic stamp head` before using `upgrade`.

## Deploy and verify (after prerequisites)

```
./scripts/build_zip.sh agents/sdlc-planner-strands
./scripts/build_zip.sh agents/release-readiness-langgraph
uv run scripts/deploy_agent.py sdlc-planner-strands build/sdlc-planner-strands.zip
uv run scripts/deploy_agent.py release-readiness-langgraph build/release-readiness-langgraph.zip
uv run scripts/smoke_test.py   # backend must be running
```

Demo prompts (doc 07 section 6):

- Planner: "Generate user stories for a password reset feature", then
  "Estimate the backlog", then "Create tickets for the approved stories"
- Release: "Assess release readiness for version 1.4.0", answer the go/no-go
  card, then "Summarize the decision"

## Card contract (single source of truth: doc 07 section 4)

| Card | Agent | Tool | Mechanism |
|---|---|---|---|
| StoryCard | planner | `show_user_stories` | backend tool, `useRenderTool` |
| EstimateTable | planner | `show_estimates` | backend tool, `useRenderTool` |
| ApprovalCard | planner | `request_ticket_approval` | frontend HITL tool, `useHumanInTheLoop` |
| ChecklistCard | release | `show_release_checklist` | graph-emitted tool call, `useRenderTool` |
| RiskMatrixCard | release | `show_risk_matrix` | graph-emitted tool call, `useRenderTool` |
| DecisionCard | release | `request_go_nogo` | LangGraph interrupt, `useInterrupt` |

Shared state: the release agent streams `{progress: {step, total, label}}`
state snapshots, rendered by the progress bar on the release chat page.

`request_ticket_approval` is deliberately not defined in the planner's
`tools.py`: CopilotKit sends the tool definition with each request and
`ag-ui-strands` registers it as a client proxy tool, so the run pauses until
the browser returns the decision (HITL). Ticket creation itself is simulated
by a `console.log` line in ApprovalCard on approval.
