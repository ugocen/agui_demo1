# Phase 0 — Debug report & implementation plan

**Date:** 2026-07-14 · **Scope:** whole `Phase0/` app (backend, frontend, 5 agents,
enterprise overlay) · **Method:** static audit (3 parallel auditors) + live
verification (smoke test against deployed AgentCore + in-browser run) + `ruff` /
`npm build` / `npm lint`.

> **Verification legend** — how much each finding was checked:
> **✅ verified** (I reproduced it in the code or at runtime this session) ·
> **◑ plausible** (single-auditor, code-cited, not independently re-verified — the
> adversarial verify pass was cut short by a spend limit) · **ℹ️ observed live**.

---

## 1. Health check — is it working?

**Yes, the core platform works end-to-end.** One lint blocker was found and fixed;
the rest are improvements, not breakage.

| Check | Result | Notes |
|---|---|---|
| `ruff check agents backend/app` | ✅ **fixed** (was FAIL) | 10× `E402` in `backend/app/main.py` (intentional `load_dotenv()` before imports). Fixed with a scoped `Phase0/ruff.toml` per-file-ignore. |
| `npm run build` (frontend) | ✅ green | Next.js 16.2.10 (Turbopack), TypeScript clean, all routes generated |
| `npm run lint` (frontend) | ✅ green | eslint clean |
| `python -c "import app.main"` (backend) | ✅ ok | boots; env layering (`backend/.env` > `Phase0/.env` > process env) works |
| Backend boot + **AgentCore catalog sync** | ✅ ok | logs: *"catalog synced from AgentCore: 5 AG-UI runtime(s)"* — live discovery works |
| **Smoke test** `scripts/smoke_test.py` (live AgentCore) | ✅ **5/5 PASS** | S1 stories · S2 estimates · S3 ticket-approval HITL · S4 readiness + 13 progress updates · S5 go/no-go interrupt |
| Browser: workspace, catalog, agent chat, A2UI connect/run | ✅ loads & runs | `/api/copilotkit/agent/a2uidemo/run` → 200; A2UI renderer mounts |

**One environmental gotcha observed live (not a code defect):** a browser A2UI run
returned **HTTP 500** whose root cause was an **expired AWS SSO session** on the
backend — `botocore ... LoginRefreshRequired: Your session has expired` raised inside
`agui_proxy.sigv4_headers` during SigV4 signing. The smoke test had passed minutes
earlier with valid credentials. **Fix on the operator side:** re-authenticate AWS
before running. **Fix in code (small):** catch credential errors in the proxy and
return a clean `503 {"detail": "backend AWS credentials expired — re-authenticate"}`
instead of an unhandled 500 stack trace (finding **M9**).

**Changes already applied this session:**
- `Phase0/ruff.toml` (new) — scoped `E402` ignore for `main.py`; ruff now clean.
- `.claude/launch.json` — added a `backend` dev-server entry (mirrors the `frontend` one) so both start from the harness.

---

## 2. Enterprise LLM parity — the explicit question, answered

> *"Enterprise agents must use the GenAI-marketplace gateway instead of Bedrock. Verify
> that local and enterprise are the same code except the LLM call."*

**✅ Confirmed — and it is stronger than "same except the LLM call": the call sites are
identical; only environment values differ.**

> **Superseded 2026-07-14 (PR #20).** The provider is no longer selected from the
> environment; the agents are forked, one copy per provider (AGENTS.md invariant 4).
> `use_gateway()` no longer exists. The section below describes the pre-fork design
> and is kept only as the record of what the audit found at the time.

- **One codebase per agent.** All five `model_factory.py` copies are **byte-identical**
  (`md5 = 71f74e15304ac62cbe74fabcbdfb8679`). Every agent builds its model **only** via
  `build_strands_model()` / `build_langchain_model()`. A grep of all agent `.py` for
  hardcoded model ids / `anthropic` / endpoints / keys finds **none** — the env-driven
  invariant holds.
- **The switch is `use_gateway()` = both `BEDROCK_ENDPOINT_URL` and `BEDROCK_API_KEY`
  set.**
  - **Default (local / personal):** Amazon Bedrock via the host credential chain
    (SigV4), default model `global.anthropic.claude-haiku-4-5`.
  - **Enterprise:** `boto3.Session(aws_access_key_id="dummy", …)` + `bedrock-runtime`
    client with `endpoint_url=<gateway>` + a `before-call` hook injecting
    `params["headers"]["x-api-key"]`. This is **exactly** the enterprise reference
    sample (dummy static creds + `endpoint_url` + `x-api-key` on `before-call` +
    `ChatBedrockConverse(model, client)`).
- **The overlay forks no code.** `cloud_deploy/` git-tracks **4 files** (README + 3 env
  templates) — zero source. Setting `BEDROCK_ENDPOINT_URL` + `BEDROCK_API_KEY` (+ the
  enterprise default model `global.anthropic.claude-sonnet-4-5`) on the AgentCore
  runtime flips gateway mode with **no code change**.
- **Operation-hook coverage is correct.** Verified from the *installed* `strands 1.47.0`
  and `langchain-aws 1.6.2` sources: both call only `Converse` / `ConverseStream` /
  `CountTokens` — **never `InvokeModel`** — so the hooked op set fully covers every live
  path. (The enterprise sample also shows an `InvokeModel` variant; we don't use it.)

**Two parity gaps to fix (see H3, L11, L12 below):** the *scripted* deploy path can't
set the gateway env vars and would wipe them on re-deploy (enterprise deploy is
console-manual today); and `BEDROCK_STREAMING` is honored only in gateway mode.

---

## 3. Prioritized findings & fixes

### 🔴 High — fix before any multi-user / enterprise deployment

**H1 — Per-agent `required_role` is stored and admin-editable but never enforced.**
`✅ verified` · `backend/app/agui_proxy.py` (proxy has no role check), `agents_catalog.py:90`
(returns `required_role`), `AgentCatalogAdmin.tsx` (edits it).
- *Impact:* in `entra` mode, restricting an agent to a role (e.g. release-readiness →
  `release-managers`) does **nothing** — any authenticated platform user can
  `POST /api/agui/{id}` to any enabled agent, and `/api/agents` lists them all. A
  security control that looks configured is a silent no-op.
- *Fix:* after `get_agent()` in `proxy_agui`, enforce
  `if user["mode"] == "entra" and agent["required_role"] and agent["required_role"] not in user["roles"]: raise HTTPException(403)`.
  Filter `/api/agents` the same way so users only see agents they may use.

**H2 — CopilotKit runtime handler is a first-request singleton: a down/empty backend on
the first request caches an empty agent list *and disables A2UI* until process restart.**
`✅ verified` · `frontend/src/app/api/copilotkit/[[...path]]/route.ts:35`.
- *Impact:* four failure modes, all until restart: (1) backend down/401 on the first
  `/api/copilotkit` request → empty agent list forever **and** A2UI middleware never
  mounts (its spread is gated on `agentIds.length > 0`); (2) agents synced after startup
  never appear (the code comment admits it); (3) the first requester's `Authorization`
  decides the cached list for everyone; (4) two concurrent first requests race. (This is
  availability/staleness, not privilege escalation — invocation authz is still enforced
  backend-side.)
- *Fix:* move the catalog fetch **inside** the async `agents` factory (the installed
  runtime's `AgentsFactory` may be async — *"multi-tenant / request-scoped"*), so it runs
  per request with that request's `Authorization`; make the A2UI middleware
  unconditional (`a2ui: { injectA2UITool: true }`, omit `agents` → applies to all).
  Optionally add a 15–30 s TTL cache; stop swallowing non-OK responses silently.

**H3 — `deploy_agent.py` cannot set gateway env vars and silently wipes them on update.**
`◑ plausible` · `scripts/deploy_agent.py:157` (`environmentVariables={"BEDROCK_MODEL_ID": model_id}` +
`update_agent_runtime`).
- *Impact:* `update_agent_runtime` **replaces** the runtime's env map with only
  `BEDROCK_MODEL_ID`, so re-running the documented deploy against a console-configured
  gateway runtime strips `BEDROCK_ENDPOINT_URL` / `BEDROCK_API_KEY` / `BEDROCK_STREAMING`
  → model_factory falls back to SigV4 Bedrock → 500s in an enterprise account with no
  Bedrock access. Also forces one global model id for every agent.
- *Fix:* read the runtime's existing `environmentVariables` (`get_agent_runtime`) and
  **merge** on update; optionally pass `BEDROCK_*` from `cloud_deploy/env/agents.env` so
  gateway deploys are scriptable.

### 🟠 Medium

**M1 — Synchronous `boto3` control-plane calls block the event loop, stalling live SSE.**
`◑ plausible` · `backend/app/agents_catalog.py:26` (`discover_runtimes` = 1 + N blocking
HTTPS calls) called from async contexts (startup, every `GET /api/agentcore/runtimes`,
admin sync). While a sync runs, uvicorn processes nothing — including chunks of every
in-flight AG-UI SSE stream. *Fix:* `runtimes = await asyncio.to_thread(discover_runtimes)`;
cache the `boto3.Session` at module scope; wrap `get_credentials()` in the proxy hot path
too.

**M2 — Unknown `AUTH_MODE` fails open (treated as no-auth).** `◑ plausible` ·
`backend/app/auth.py:360`. A typo (`entraid`, `azure`, `sso`) silently disables **all**
auth — including `/api/admin/*` — with only a log warning, contradicting the file's own
fail-closed design. *Fix:* raise `500 "unknown AUTH_MODE"` for anything not in
`{iam, off, "", entra}`.

**M3 — AgentCore session id is client-controlled and not bound to user identity.**
`◑ plausible` · `backend/app/agui_proxy.py:44`. The upstream session id is derived
verbatim from the request `threadId`. In `entra` mode, a user who learns another's
`threadId` is routed to the **same AgentCore runtime session** (same microVM state) —
cross-user session reuse (threadIds are UUIDs, so guessing is hard, but there's no
server-side binding). *Fix:* derive it server-side as `sha256(f"{oid}:{thread_id}")`,
preserving per-user HITL-resume affinity.

**M4 — Entra access token acquired once on mount, never refreshed → all calls 401 after
~1 h.** `◑ plausible` · `frontend/src/components/AuthGate.tsx:47`. The effect deps never
change post-sign-in, so `acquireTokenSilent` runs once; Graph tokens expire ~60–90 min,
after which every fetch (and the `Authorization` forwarded through `/api/copilotkit`)
carries an expired token. Combined with **H2**, an expired-token first request can poison
the runtime for everyone. *Fix:* schedule renewal from `result.expiresOn` (renew ~5 min
early); or centralize fetch with a 401→`forceRefresh` retry.

**M5 — Reopening a thread from history resets its title and `createdAt`.** `◑ plausible` ·
`frontend/src/components/AgentChat.tsx:105` + `lib/threads.ts` (`upsertThread` full-
replaces). Clicking a history item upserts a fresh record (title = agent name, time =
now), clobbering the stored title/timestamp. *Fix:* make `upsertThread` merge-preserving
(keep existing `title`/`createdAt` when present).

**M6 — Documented `LOCAL_AGENT_URL_RELEASE` local-dev mode no longer exists in the code.**
`✅ verified` · `AGENTS.md:89`, `Phase0/README.md:95`, `agents/a2ui-demo-strands/agent.py:9`
document it; `grep LOCAL_AGENT Phase0/backend/app` → nothing (removed in commit `f98cff8`
when routing moved to the DB catalog). Setting the env var does nothing. *Fix:* **either**
delete the stale paragraphs (docs match reality) **or** reinstate the override in
`agui_proxy.py` (check `os.environ.get(f"LOCAL_AGENT_URL_{id.upper()}")` before the ARN
lookup, skip SigV4 for local URLs). Recommend: delete the docs for Phase 0; reinstate only
if AWS-free local runs are wanted back.

**M7 — `ui_mode` is a dead field end-to-end (stored, validated, returned; read by
nothing).** `✅ verified` · `backend/app/models.py:45` + returned by 3 endpoints; frontend
grep for `ui_mode`/`uiMode` → only a comment in `AgentChat.tsx:19`; admin UI dropped the
column. Flipping it changes nothing; stale docstrings (`admin.py:7-9`,
`catalog_service.py:52-54`) still claim `static` yields hand-authored cards. *Fix
(decision):* this is the **`render_mode` extension** the SUNUM deck describes. Either
**(a)** wire it live (gate per-agent `useRenderTool` bindings on `ui_mode`, re-expose the
admin control — ~1–2 days; see the deck's Part 7), or **(b)** remove it end-to-end (model
+ `EDITABLE_FIELDS`/`UI_MODES` + admin validation + 3 API payload keys + a SQLite
migration + fix the docstrings). **Recommend (a)** — it delivers the presentation's
"backward-compat + flexibility" story.

**M8 — 🔒 A real enterprise gateway API key sits in plaintext on disk.** `✅ verified` ·
`cloud_deploy/agents/.env` — a `BEDROCK_API_KEY=<real value>` (untracked, gitignored;
value **not** reproduced here). *Impact:* one `git add -f`, `.gitignore` edit, or
directory share from leaking; any local tool reading the tree sees it. *Fix:* **rotate the
key** (it has sat in a working tree), delete `cloud_deploy/agents/.env` per the overlay
README's own guidance, and keep the key only in AgentCore runtime env vars (console) or a
transient `Phase0/agents/.env` while testing.

**M9 — Credential-refresh failure in the proxy surfaces as an unhandled 500 stack trace.**
`ℹ️ observed live` · `backend/app/agui_proxy.py:60` (`sigv4_headers`). When AWS SSO creds
expire, `get_frozen_credentials()` raises `LoginRefreshRequired`, which propagates as a
raw ASGI 500 (full traceback) to the browser (seen this session). *Fix:* catch
`botocore.exceptions` around the signing call and return
`503 {"detail": "backend AWS credentials expired — re-authenticate (aws sso login)"}`.

### 🟡 Low (polish / hardening)

| ID | Finding | File | Fix |
|---|---|---|---|
| L1 | CORS origin hardcoded `http://localhost:3000` (not env-configurable; breaks the env-only overlay for another origin) | `backend/app/main.py:62` | `allow_origins=os.environ.get("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")` |
| L2 | Graph `checkMemberGroups` not chunked — 400s (fail-closed → total lockout) past 20 configured groups | `backend/app/auth.py:265` | chunk group ids into batches of 20, union results |
| L3 | Auth TTL cache unbounded, evicts only on read (slow leak on long-lived process) | `backend/app/auth.py:72` | sweep expired entries, or `cachetools.TTLCache(maxsize=…)` |
| L4 | `useInterrupt` renderer is a catch-all: any interrupt lacking a `tool` field renders the Go/No-Go card | `frontend/.../HumanInTheLoop.tsx:242` | invert to opt-in: only `request_go_nogo` → GoNoGo; else a generic interrupt card |
| L5 | `ChartView` can't recover after a render error (canvas unmounted → effect early-returns forever) | `frontend/.../richCatalog.tsx:152` | keep the canvas mounted; `setError(null)` at effect top when `depKey` changes |
| L6 | Sidebar shows "Backend unreachable" while the catalog fetch is still in flight | `frontend/.../WorkspaceShell.tsx:121` | track `CatalogAgent[] \| null` (null = loading); reserve the error label for the catch branch |
| L7 | `/a2ui-preview` page bypasses `AuthGate` (renders unauthenticated in entra mode) | `frontend/src/app/a2ui-preview/page.tsx` | wrap in `<AuthGate>` (no-op in iam) or exclude from prod builds |
| L8 | Thread history doesn't sync across tabs (same-tab custom event only) | `frontend/src/lib/threads.ts:34` | also subscribe to the native `storage` event |
| L9 | `msalInstance` constructed at module scope even in `iam` mode | `frontend/src/lib/msal.ts:5` | lazy `getMsalInstance()` (client + entra only); dynamic-import msal |
| L10 | `requirements.txt` pin drift — `sdlc-planner` lacks the `fastapi==0.139.0` pin the other Strands agents carry | `agents/sdlc-planner-strands/requirements.txt` | add the pin, or drop it from all (AGUIApp needs only starlette) |
| L11 | `BEDROCK_STREAMING` honored only in gateway mode (docs imply it's general) | `agents/*/model_factory.py:59` | pass `streaming`/`disable_streaming` in the non-gateway branch too (mirror to all 5 copies) |
| L12 | Gateway `x-api-key` hook covers only the Converse family (defense-in-depth; **not** a live bug — no path calls `InvokeModel`) | `agents/*/model_factory.py:81` | also register `InvokeModel`/`InvokeModelWithResponseStream`, or add a comment stating the Converse-only invariant |

### 🔵 Watch item (verify, don't refactor speculatively)

**W1 — AgentCore memory-replay on reconnect/resume.** Documented in
`docs/COPILOTKIT-NATIVE-MIGRATION.md`: AgentCore server-side session memory can, on
replay, return an empty snapshot for an unknown thread and omit `TOOL_CALL_RESULT`
events, leaving tool calls unpaired — which the thin proxy pipes through unmodified. The
sharpest trigger is the **release agent's LangGraph `interrupt()`** resumed after a
browser reload. *Action:* run the concrete test in that doc (§Task 5) **before the SUNUM
demo**; if it reproduces, port `@copilotkit/agentcore-runner`'s two fixes into
`agui_proxy.py` (keeps the auth boundary); if not, log as known-watch.

---

## 4. Sequenced implementation plan

**Sprint A — correctness & security (do first).** H1 (enforce `required_role`) · M2
(fail-closed AUTH_MODE) · M8 (rotate + remove the on-disk key) · M9 (clean credential-
error response) · M3 (bind session id to user). *Rationale: these are the gates before
any multi-user `entra` deployment. All backend-local, small diffs.*

**Sprint B — reliability.** H2 (async agents factory + unconditional A2UI) · M1
(`asyncio.to_thread` for boto3) · M4 (token refresh) · M5 (thread merge) · L5/L6 (chart
recovery, loading state). *Rationale: removes the "works until it doesn't" foot-guns
(stale runtime, hourly 401s, event-loop stalls).*

**Sprint C — the `render_mode` story (product value).** M7 option (a): gate per-agent
`useRenderTool` bindings on `ui_mode`, re-expose the admin control, rename toward
`render_mode`, add a `plain`/non-AG-UI path. *Rationale: this is the presentation's
headline capability; it's the difference between "designed" and "demoable."* Pairs with
the SUNUM deck's Part 7 and its `[research this]` items #6–#8.

**Sprint D — enterprise deploy parity.** H3 (merge env on `update_agent_runtime`; make
gateway vars scriptable) · L11 (streaming flag in default mode) · L12 (hook comment/extra
ops). *Rationale: makes the enterprise gateway deploy reproducible, not console-manual.*

**Sprint E — docs & polish.** M6 (delete or reinstate `LOCAL_AGENT_URL`) · L1 (CORS env)
· L2/L3 (Graph chunking, cache bound) · L7–L10 (auth-gate preview, cross-tab threads,
lazy msal, requirements pin). · W1 test.

**Continuous:** after each change run `cd Phase0 && ruff check agents backend/app` and
`cd Phase0/frontend && npm run build && npm run lint` (both green today); re-run
`scripts/smoke_test.py` after backend changes (needs valid AWS creds + a running backend).

---

## 5. What was NOT independently re-verified

The adversarial verification pass (independent skeptics per finding) was **cut short by a
monthly spend limit**, so most `◑ plausible` findings are single-auditor, code-cited but
not re-challenged. Before implementing H3, M1–M5, re-read the cited lines to confirm the
exact call shape. The `✅ verified` items (H1, H2, M6, M7, M8, M9, the parity result, the
health checks) I reproduced directly this session.
