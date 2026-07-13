# Phase 0 Implementation Plan for Claude Code (End-to-End Executable)

This document is written to be handed directly to Claude Code. It builds the Phase 0 validation spike from docs 01, 02 and 06: two SDLC-themed AG-UI agents on Amazon Bedrock AgentCore (one Strands, one LangGraph), a local FastAPI backend, and a local Next.js + CopilotKit frontend that renders different generative UI cards per agent.

## 0. Rules for the Executing Agent

* Execute tasks strictly in order (T1 → T8). Do not start a task before the previous task's "Done when" check passes
* After every task, run the Verify commands and show the output. If verification fails, fix it before moving on, do not skip
* Tasks marked [Human] cannot be done by you. Stop, print exactly what the human must do, and wait for confirmation
* Read configuration only from `.env` (template in section 7). Never hardcode account IDs, ARNs, secrets, or region
* Keep code simple and explicit. Few comments, never on the same line as code, English only. No clever abstractions, this is a spike
* Pin dependency versions in requirements/package files at install time and record them in `phase0/VERSIONS.md`
* If an AWS API call fails, consult the failure playbook in section 8 before retrying

## 1. Scope

In scope: two AG-UI agents deployed to AgentCore via direct code deployment (zip in S3), packaging and deploy scripts, local FastAPI backend (AG-UI proxy + auth), local Next.js CopilotKit frontend with per-agent cards, smoke tests mapping to gate G0.

Out of scope: EKS, Temporal, CI/CD pipelines, registries, MCP servers, production hardening. Database is optional, use SQLite via SQLAlchemy only if a task needs persistence.

## 2. Prerequisites [Human]

* H1: AWS credentials configured locally (`aws configure`) for the IAM deployment user (Stage A, personal account) or the assigned role (Stage B, corporate account). Set `AWS_REGION` in `.env`
* H2: Bedrock model access enabled in that region for the model in `BEDROCK_MODEL_ID`
* H3: An S3 bucket for deployment packages, name in `DEPLOY_BUCKET` (the deploy script can create it if the credentials allow)
* H4: Auth mode decision: `AUTH_MODE=iam` (Stage A fallback) or `AUTH_MODE=entra` with the Entra values from section 7 filled in
* H5: Toolchain installed: Python 3.13, `uv`, Node.js 20+, `zip` (on Windows: run packaging inside WSL, see doc 02 step 3)

## 3. Workspace Layout (created in T1)

```
phase0/
├── .env                # copied from .env.example, filled by human
├── VERSIONS.md
├── agents/
│   ├── sdlc-planner-strands/
│   │   ├── agent.py
│   │   ├── tools.py
│   │   └── requirements.txt
│   └── release-readiness-langgraph/
│       ├── agent.py
│       ├── graph.py
│       └── requirements.txt
├── backend/
│   ├── app/main.py
│   ├── app/auth.py
│   ├── app/agui_proxy.py
│   ├── app/agents_catalog.py
│   └── requirements.txt
├── frontend/            # Next.js app, created with create-next-app
│   └── src/components/cards/
└── scripts/
    ├── build_zip.sh
    ├── deploy_agent.py
    └── smoke_test.py
```

## 4. Shared Contract, the Card Catalog

A "card" is a frontend React component that CopilotKit renders when the agent calls a specific tool. The tool's return payload is the card's props. Both sides must match this table exactly. Note: CopilotKit provides the ready-made chat shell (chat/sidebar components, streaming, input) and the rendering mechanism (render hooks, HITL render-and-wait, shared state), but it ships no domain cards, every card below is a small custom component we write and register for its tool name. Unregistered tools fall back to CopilotKit's generic tool-call rendering.

| Card component | Agent | Tool name | Payload schema (JSON) |
|---|---|---|---|
| StoryCard | planner | `show_user_stories` | `{stories: [{id, title, acceptance_criteria: [string], priority: "high"\|"medium"\|"low"}]}` |
| EstimateTable | planner | `show_estimates` | `{items: [{story_id, points: number, confidence: "high"\|"medium"\|"low"}]}` |
| ApprovalCard (HITL) | planner | `request_ticket_approval` | `{summary: string, tickets: [{title, points}]}` → user returns `{decision: "approved"\|"rejected", note?: string}` |
| ChecklistCard | release | `show_release_checklist` | `{release: string, items: [{name, status: "pass"\|"fail"\|"warn", detail: string}]}` |
| RiskMatrixCard | release | `show_risk_matrix` | `{risks: [{name, probability: 1-5, impact: 1-5, mitigation: string}]}` |
| DecisionCard (HITL) | release | `request_go_nogo` | `{recommendation: "go"\|"no-go", reasons: [string]}` → user returns `{decision: "go"\|"no-go", note?: string}` |

Shared state (AG-UI state events): the release agent maintains `{progress: {step: number, total: number, label: string}}` and updates it as graph nodes complete, the frontend shows it as a progress indicator.

## 5. Tasks

### T1, Scaffold the workspace

Steps: create the layout from section 3, write `.env.example` (section 7), initialize git in `phase0/`, create `VERSIONS.md` with a header.
Verify: `find phase0 -type d | sort` matches the layout.
Done when: layout exists and `.env.example` is complete.

### T2, Agent A, "SDLC Planner" (Strands + AG-UI)

SDLC role: backlog refinement and sprint planning assistant. Scenarios it must handle:

* S1, story generation: user describes a feature, the agent drafts 3 to 5 user stories with acceptance criteria and calls `show_user_stories` once with all of them (renders StoryCards)
* S2, estimation: on request, the agent assigns story points to the current stories and calls `show_estimates` (renders EstimateTable)
* S3, ticket creation with approval: when asked to create tickets, the agent must NOT claim creation directly, it calls `request_ticket_approval` (HITL), waits for the user decision, then confirms the outcome in text. Ticket creation itself is simulated (log line), no external system in Phase 0

Implementation instructions:

* `requirements.txt`: `strands-agents`, `ag-ui-strands`, `bedrock-agentcore`, plus the AG-UI server dependencies they pull in. Pin versions
* `tools.py`: one function per tool in the card table. Each tool validates its input, builds the exact payload schema, and returns it. Keep tools deterministic, the LLM decides content, tools only shape it
* `agent.py` skeleton:

```python
import os
from strands import Agent
from strands.models import BedrockModel
from ag_ui_strands import create_strands_fastapi_app
from tools import show_user_stories, show_estimates, request_ticket_approval

SYSTEM_PROMPT = """You are an SDLC planning assistant.
For story generation call show_user_stories exactly once with all stories.
For estimation call show_estimates.
Never create tickets without calling request_ticket_approval first and waiting for the decision.
Keep chat text short, the cards carry the detail."""

model = BedrockModel(model_id=os.environ["BEDROCK_MODEL_ID"])
agent = Agent(model=model, system_prompt=SYSTEM_PROMPT,
              tools=[show_user_stories, show_estimates, request_ticket_approval])
app = create_strands_fastapi_app(agent)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

* If the pinned `ag-ui-strands` version exposes a different app factory name, adapt to the library's documented API, the structural intent stays: Strands agent wrapped as an AG-UI FastAPI app serving `/invocations` style endpoints on port 8080
* HITL: implement `request_ticket_approval` using the AG-UI/CopilotKit HITL pattern supported by the pinned library version (tool result deferred to the frontend response)

Verify: `python agent.py` locally, then `curl -s localhost:8080/ping` returns healthy, and a local AG-UI POST with prompt "Generate user stories for a password reset feature" streams events containing a `show_user_stories` tool call.
Done when: S1 and S2 produce correct payloads locally and the process runs clean.

### T3, Agent B, "Release Readiness" (LangGraph + AG-UI)

SDLC role: pre-deployment release assessment. Scenarios:

* S4, readiness assessment: user asks "assess release readiness for version X". The graph runs three nodes in order, `collect_checks` (simulated CI, coverage, open-bug data), `assess_risks`, `recommend`. After node 1 it calls `show_release_checklist`, after node 2 `show_risk_matrix`, and it updates the shared `progress` state as each node completes
* S5, go/no-go decision: the final node calls `request_go_nogo` (HITL) with its recommendation, waits for the human decision, then summarizes in text

Implementation instructions:

* `requirements.txt`: `langgraph`, `langchain-aws` (Bedrock chat model), `ag-ui-langgraph`, `bedrock-agentcore`. Pin versions
* `graph.py`: a `StateGraph` with state `{version: str, checks: list, risks: list, progress: dict}` and the three nodes above. Simulated check data lives in a small dict inside the node, clearly marked as fixture data
* `agent.py`: wrap the compiled graph with the `ag-ui-langgraph` FastAPI helper (e.g., `add_langgraph_fastapi_endpoint`) serving on port 8080, emit state updates so `progress` reaches the frontend as AG-UI state events, implement `request_go_nogo` with LangGraph's interrupt mechanism mapped to AG-UI HITL
* Keep the graph linear, no branching, this is deliberately the simplest graph that proves multi-step streaming and interrupts

Verify: local run, `curl /ping` healthy, prompt "Assess release readiness for version 1.4.0" streams progress state updates plus `show_release_checklist` and `show_risk_matrix` tool calls, and pauses on `request_go_nogo`.
Done when: S4 streams all three artifacts in order and S5 interrupt resumes after a simulated decision.

### T4, Packaging script

`scripts/build_zip.sh <agent-dir>`:

* Creates `build/<agent>/package/`, installs dependencies with `uv pip install --python-platform aarch64-manylinux2014 --only-binary=:all: -r requirements.txt --target build/<agent>/package/`
* Copies the agent's `.py` files to the package root
* Sets permissions (644 files, 755 dirs), zips from inside the package folder to `build/<agent>.zip`
* Fails loudly if the zip exceeds 250 MB or any `.so` is not ARM64 (check with `file` where available)

Verify: run for both agents, `unzip -l` shows `agent.py` at the zip root.
Done when: both zips build reproducibly.

### T5, Deploy script

`scripts/deploy_agent.py <agent-name> <zip-path>`:

* Uploads the zip to `s3://$DEPLOY_BUCKET/<agent-name>/deployment_package.zip`
* Calls `create_agent_runtime` (or `update_agent_runtime` if it exists) on the `bedrock-agentcore-control` client with: `codeConfiguration` artifact (bucket + key, runtime `PYTHON_3_13`, entryPoint `["agent.py"]`), protocol `AGUI` in the protocol configuration, network mode `PUBLIC`, execution role from `EXECUTION_ROLE_ARN`, and when `AUTH_MODE=entra` a JWT authorizer with `ENTRA_DISCOVERY_URL` and `ENTRA_ALLOWED_AUDIENCE`
* Prints the runtime ARN and writes it to `.env` as `PLANNER_RUNTIME_ARN` / `RELEASE_RUNTIME_ARN`
* [Human] alternative: the same deployment can be done through the AWS console following doc 02 "Phase 0 deployment procedure", the script and the console produce identical runtimes

Verify: deploy both agents, script exits 0, ARNs written, `get_agent_runtime` shows READY status.
Done when: both runtimes are READY and each answers a test invocation.

### T6, Local FastAPI backend

* `app/auth.py`: if `AUTH_MODE=entra`, validate bearer JWTs against the Entra JWKS (issuer + audience checks), extract `roles` claim, reject missing role `platform.user` with 403. If `AUTH_MODE=iam`, skip validation and sign upstream calls with SigV4
* `app/agents_catalog.py`: static list of the two agents `{id, name, description, runtime_arn, capability: "agui"}` read from `.env`, exposed at `GET /api/agents`
* `app/agui_proxy.py`: `POST /api/agui/{agent_id}` streams the AG-UI request to the runtime's invocation endpoint and pipes the SSE stream back unchanged, forwarding the user's bearer token (entra mode) or SigV4 signing (iam mode). Use `httpx` streaming, no buffering
* `app/main.py`: FastAPI wiring, CORS for `http://localhost:3000`

Verify: `uvicorn app.main:app` runs, `/api/agents` lists both agents, a curl through the proxy streams events from the planner runtime.
Done when: both runtimes reachable end to end through the proxy with the configured auth mode.

### T7, Frontend, Next.js + CopilotKit

* Create with `create-next-app` (TypeScript, App Router), add CopilotKit pinned to the current major. Version note: in CopilotKit v2 the prebuilt components (`CopilotChat`, `CopilotSidebar`, `CopilotPopup` plus building blocks `CopilotChatView`, `CopilotChatMessageView`, `CopilotChatInput`, message components) import from `@copilotkit/react-core/v2` with its `styles.css`, the legacy 1.x path was `@copilotkit/react-ui`. Follow the pinned major's docs. Self-hosted runtime as a Next.js API route pointing at the backend proxy per the CopilotKit self-hosting guide (production-style `selfManagedAgents`, never the dev-only direct connection)
* Sign-in: `AUTH_MODE=entra` uses MSAL (SPA app registration, PKCE) and attaches the access token to backend calls, `AUTH_MODE=iam` skips sign-in
* Agent picker page from `GET /api/agents`, selecting an agent mounts a CopilotKit chat bound to that agent
* `src/components/cards/`: one component per card in section 4, registered for the matching tool names via `useRenderTool` / `useRenderToolCall` (v2) with `useDefaultRenderTool` as the fallback for unregistered tools. ApprovalCard and DecisionCard use the HITL mechanism (`useHumanInTheLoop`, or `useInterrupt` for the LangGraph interrupt) returning the decision payload
* Release agent page additionally subscribes to shared state and renders the `progress` indicator
* Styling minimal, correctness over beauty

Verify: `npm run dev`, run scenarios S1 to S5 in the browser, each expected card renders, HITL buttons resume the agent.
Done when: every card in section 4 has rendered at least once from a live agent.

### T8, Smoke tests and G0 mapping

`scripts/smoke_test.py` runs the scripted checks and prints a G0 report:

* S1 prompt returns a `show_user_stories` tool call with 3 to 5 stories
* S2 returns `show_estimates` covering the story ids from S1
* S3 pauses on `request_ticket_approval` and completes after an approval payload
* S4 streams progress state, checklist, and risk matrix in order
* S5 pauses on `request_go_nogo` and resumes on decision
* Entra mode only: request without a token gets 401, token without the app role gets 403
* Kill the running stream mid-way once, confirm the frontend surfaces the error without crashing (manual step, print instructions)

Done when: the report shows all automated checks green, remaining G0 items (Stage B corporate rerun, AG-UI go/no-go decision) are listed as [Human] follow-ups.

## 6. Demo Script (exact prompts for the human)

* Planner: "Generate user stories for a password reset feature", then "Estimate the backlog", then "Create tickets for the approved stories"
* Release: "Assess release readiness for version 1.4.0", answer the go/no-go card, then ask "Summarize the decision"

## 7. .env.example

```
AWS_REGION=
BEDROCK_MODEL_ID=
DEPLOY_BUCKET=
EXECUTION_ROLE_ARN=
AUTH_MODE=iam
ENTRA_TENANT_ID=
ENTRA_DISCOVERY_URL=
ENTRA_ALLOWED_AUDIENCE=
ENTRA_SPA_CLIENT_ID=
PLANNER_RUNTIME_ARN=
RELEASE_RUNTIME_ARN=
BACKEND_URL=http://localhost:8000
```

## 8. Failure Playbook

* "incompatible with Linux ARM64": a dependency was installed for the wrong platform, rebuild with the exact `uv` flags in T4, never plain `pip install`
* Access denied on create/update runtime mentioning S3: the calling identity lacks `s3:GetObject` on the zip (add it), or `kms:Decrypt` if the bucket uses a CMK
* "entrypoint could not be found": the path inside the zip does not match `entryPoint`, re-zip from inside the package folder so `agent.py` is at the root
* 401/403 from the runtime in entra mode: check the JWT authorizer's discovery URL and allowed audience match the token's `iss` and `aud`, decode the token locally to compare
* Runtime stuck not READY: check CloudWatch Logs for the runtime, most often an import error from a missing dependency in the zip
* Frontend renders no cards: tool name mismatch between agent and card registration, diff both against the section 4 table, it is the single source of truth
