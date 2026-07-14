# Evaluation — adopting CopilotKit's native runners/packages

Status: **evaluation only** (no code change). Decides how much of CopilotKit's
first-party surface Phase 0 should adopt in place of hand-built equivalents, and
flags one latent correctness risk (AgentCore memory replay).

## Framing

Phase 0 **already uses CopilotKit** as a library: the frontend mounts
`<CopilotKitProvider>` + `<CopilotChat>` (v2 subpath APIs), a self-hosted
CopilotKit **runtime** in the Next.js route `app/api/copilotkit/[[...path]]`
registers each agent as an `HttpAgent` pointing at the FastAPI proxy
(`/api/agui/{id}`), and A2UI is rendered with `@copilotkit/a2ui-renderer`. So the
question is **not** "bespoke FE vs CopilotKit FE" — it is "keep hand-building the
runner/catalog/persistence glue, or adopt CopilotKit's first-party packages for
it?"

**Version alignment (important):** Phase 0 pins CopilotKit **1.62.3** and
`@ag-ui/client` **0.0.57**; the CopilotKit monorepo checkout is **also 1.62.3**.
The reference app below is therefore directly compatible — same API surface, no
version bridging.

## Three hand-built pieces with first-party equivalents

| Phase 0 hand-built | CopilotKit package | What it buys | Gap it closes |
|---|---|---|---|
| `backend/app/agui_proxy.py` (SigV4 + unbuffered SSE pipe to AgentCore) | **`@copilotkit/agentcore-runner`** (`AgentCoreRunner extends InMemoryAgentRunner`, runs inside CopilotRuntime) | Fixes AgentCore server-side **memory-replay** edge cases (see below); OSS | The proxy pipes SSE **unchanged** — it does not repair replay |
| `frontend/src/components/a2ui/richCatalog.tsx` (`createCatalog` + `zod/v3`) | **`@copilotkit/a2ui-renderer`** (already used) | Official `createCatalog` + v2 A2UI message-renderer wiring; a supported home for the `zod/v3` schema-extraction dependency | The `zod/v3`-vs-zod-4 two-copy fragility (PR "declare a2ui-renderer" deferred the deep fix here) |
| `backend` SQLite catalog (`models.py`/`db.py`) **+** `localStorage` thread history (`lib/threads.ts`) | **`@copilotkit/sqlite-runner`** | Server-side **thread/message persistence** (cross-device history, reopenable threads) | Phase 0 stores threads **client-side only**; the SQLite DB is the agent *catalog*, a different concern — sqlite-runner is about *threads*, not the catalog |

## The single best starting point

`CopilotKit-main/examples/integrations/agentcore/` — a complete reference app on
**exactly Phase 0's stack**: a Vite + React **CopilotKit v2** frontend, a
**Strands _or_ LangGraph** agent on **AgentCore**, a Node **CopilotRuntime bridge
Lambda** (`infra-cdk/lambdas/copilotkit-runtime/src/runtime.ts`), **Cognito OIDC**
auth, and both **CDK** (`infra-cdk/`) **and Terraform** (`infra-terraform/`) IaC.
Architecture: `Browser → API GW → CopilotKit Lambda (AG-UI bridge) → AgentCore
Runtime → strands_agent.py`.

Use it two ways:
1. **Now:** as the reference for wiring `AgentCoreRunner` and the v2 provider.
2. **Phase 1:** lift its **CDK/Terraform** as the starting IaC (Phase 0 has none;
   Phase 1's goal is real infra).

## The connection-mode decision (and why it isn't a drop-in swap)

CopilotKit offers two ways for the FE to reach agents:

- **(A) Node CopilotRuntime + a runner** (`runtimeUrl`): stand up
  `@copilotkit/runtime` v2 with `new CopilotRuntime({ agents, runner: new
  AgentCoreRunner() })`. This is what unlocks the memory-replay fix, threads,
  and MCP-apps middleware. It is what the reference app does.
- **(B) Direct AG-UI** (`agents` prop with your own `HttpAgent`s): no Node
  runtime needed.

Phase 0 today is a **hybrid**: it runs a CopilotKit runtime (in the Next route)
with `HttpAgent` → **the FastAPI backend** → SigV4 → AgentCore.

> **Key tension:** Phase 0 deliberately puts **Entra validation (Layer A) and
> SigV4 (Layer B)** in the **FastAPI backend** (`ARCHITECTURE.md` §4). Adopting
> `AgentCoreRunner` means the CopilotRuntime calls AgentCore **directly**, which
> moves the SigV4 signing — and the trust boundary — out of the FastAPI backend
> into the runtime host. So this is **not** a free swap: either (a) run
> `AgentCoreRunner` inside a runtime that sits **behind** the same auth boundary
> (e.g. the FastAPI/BFF still front-authenticates, runtime runs server-side), or
> (b) keep the FastAPI proxy and instead **port just the two replay fixes** into
> it. Do not move the AgentCore call to the browser or an unauthenticated Lambda.

## Task 5 — AgentCore memory-replay risk

**What the bug is** (why `AgentCoreRunner` exists): AgentCore's server-side
session memory, on replay, (1) returns an **empty snapshot for an unknown
thread** and (2) can **omit `TOOL_CALL_RESULT`** events, leaving tool calls
unpaired. A naive client that trusts the replayed stream then renders a broken or
empty conversation. `AgentCoreRunner` papers over both: it treats the unknown-
thread snapshot as empty-not-error and **synthesises the missing
`TOOL_CALL_RESULT`**.

**Why Phase 0 may be exposed:** `agui_proxy.py` pipes the AgentCore SSE stream
**unbuffered and unmodified**, and derives the AgentCore session-id from
`threadId`. So a brand-new thread (unknown session) and any flow that pauses on a
tool call are exactly the two triggers — most sharply the **release agent's
LangGraph `interrupt()` go/no-go**, which pauses mid-run on a tool call and
relies on session state across the resume.

**Concrete test (do this before the SUNUM demo):**
1. Run the release agent end-to-end; at the go/no-go interrupt, **reload the
   browser / reconnect** so the run resumes from AgentCore session memory.
2. Watch the proxied SSE (backend logs / devtools) for a `TOOL_CALL_START`
   without a matching `TOOL_CALL_RESULT`, and confirm the resumed conversation
   still renders the earlier checklist/risk tool calls (not an empty snapshot).
3. Repeat starting a **fresh thread** immediately after a deploy (cold session).

**Recommendation:** if step 2/3 reproduces a broken replay, either adopt
`AgentCoreRunner` (mode A, respecting the auth boundary above) or port its two
fixes into `agui_proxy.py` (cheaper, keeps the boundary). If it does not
reproduce, log it as a known-watch item — do not refactor speculatively.

## Licensing / cost

CopilotKit's **`intelligence`, threads, and memory** features are gated behind a
`COPILOTKIT_LICENSE_TOKEN` (`runtime.ts:132`). **`AgentCoreRunner` itself is fully
OSS** and needs no token. Settle which features are OSS vs licensed **before**
committing Phase 1 budget.

## What to KEEP (don't let a migration eat these)

The bespoke shell is Phase 0's differentiated value and CopilotKit does **not**
provide it: the **Entra SSO gate** (`AuthGate.tsx`), the **agent-catalog + admin
screen + audit log** (`admin/`, `catalog_service.py`), the **DB-backed generic
catalog** (no per-agent code), and the **generic A2UI** approach. Adopt runners
under the hood; keep the shell.

## Recommended sequencing

1. **Now (cheap, no arch change):** run the memory-replay test above; borrow
   CopilotKit's dev **skills** (`copilotkit-agui`, `a2ui-renderer`,
   `copilotkit-integrations`) as references.
2. **Small (this repo):** if replay reproduces, port the two `AgentCoreRunner`
   fixes into `agui_proxy.py` — smallest change that keeps the auth boundary.
3. **Phase 1:** lift the reference app's **CDK/Terraform**; evaluate moving to a
   real CopilotRuntime host with `AgentCoreRunner` **behind** the auth boundary,
   and server-side threads via `sqlite-runner`/Postgres (replacing `localStorage`).
4. **Defer:** full v2 `createCatalog` migration + zod single-instance dedup —
   only worth it alongside step 3.

## Evidence

CopilotKit monorepo: `packages/agentcore-runner/src/agentcore-runner.ts`,
`packages/a2ui-renderer/`, `packages/sqlite-runner/`,
`examples/integrations/agentcore/` (frontend + `infra-cdk/` + `infra-terraform/`),
`skills/*/SKILL.md`. Phase 0: `backend/app/agui_proxy.py`,
`frontend/src/app/api/copilotkit/[[...path]]/route.ts`,
`frontend/src/components/a2ui/richCatalog.tsx`, `frontend/src/lib/threads.ts`.
