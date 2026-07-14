# CopilotKit — adoption report (UI layer)

**Question set (from the brief):** *Are there features we can take from
CopilotKit? Why don't we use the `CopilotKit-main` folder as our UI? If we wanted
CopilotKit's UI while keeping our extra features (backend largely unchanged), what
path — and do you recommend it?*

**Companion doc:** `docs/COPILOTKIT-NATIVE-MIGRATION.md` already covers the
**backend-runner** angle (`agentcore-runner`, `sqlite-runner`, the memory-replay
risk). This report covers the **frontend / UI-layer** question and the strategic
recommendation. Read both together.

---

## TL;DR / recommendation

**We already ARE using CopilotKit's UI layer** — the current one. `CopilotKit-main`
is the **library monorepo** (pnpm/nx workspace: `packages/`, `examples/`,
`sdk-python/`, `docs/`), **not an application**. Our chat surface *is* CopilotKit's
own `<CopilotChat>` from `@copilotkit/react-core/v2`, and every CopilotKit package
we run is pinned to **1.62.3 — the exact version the monorepo builds, and npm's
latest.** There is no newer/better UI code to "switch to."

So the real question is *"adopt **more** of CopilotKit's prebuilt surface?"* — and
the answer is:

> **STAY on our app shell. PARTIALLY ADOPT 2–3 more prebuilt CopilotKit v2 pieces
> (Inspector, Suggestions, and — high value for an SDLC platform — `useFrontendTool`).
> Do NOT adopt any example app as a scaffold** (that deletes our differentiators and
> costs ~2–3 engineer-weeks to get back to parity). Treat CopilotKit **Cloud /
> Intelligence** (persisted threads, memory) as a **procurement + data-governance**
> decision, not an engineering one.

---

## Q1 — Why don't we use the `CopilotKit-main` folder as our UI?

Three concrete reasons, each evidence-backed:

**1. It's the library source, not an app.** Root `package.json` is
`"name": "CopilotKit", "private": true`, built with **Nx** (`nx run-many -t build
--projects=packages/**`), pnpm workspace. There is **no runnable product app at the
root** — only `packages/*` (the npm libraries), `examples/*` (single-agent
starters), `sdk-python/` (the `copilotkit` PyPI package), and `docs/`.

**2. We already consume its packages, at the latest version.** Our
`Phase0/frontend/package.json` pins `@copilotkit/react-core`, `@copilotkit/runtime`,
`@copilotkit/a2ui-renderer` all at **1.62.3**; the monorepo's `packages/*` are
**also 1.62.3**; `npm view @copilotkit/react-core version` → **1.62.3**. Same major,
minor, patch. "Using CopilotKit-main as our UI" cannot mean *newer code* — we have
all of it. In v2, `@copilotkit/react-core` **is** the UI package (its
`src/v2/components/chat/` ships `CopilotChat`, `CopilotSidebar`, `CopilotPopup`,
`CopilotThreadsDrawer`, attachments, audio, suggestions). The separate
`@copilotkit/react-ui` is the **v1** UI — legacy relative to our stack.

**3. Every example is a single-agent starter that lacks our 9 differentiators.**
The closest example by *deployment target* is `examples/integrations/agentcore/`,
but by *architecture* it is the furthest: **Vite (not Next.js)**, **Cognito (not
Entra)**, a **Node/Lambda AG-UI bridge (not our FastAPI SigV4 proxy)**, and a single
hardcoded `default` agent. Adopting it means re-porting almost everything we built.

### What CopilotKit does NOT ship — our 9 custom features

| # | Our feature | Files | Why CopilotKit can't give it |
|---|---|---|---|
| 1 | **Dual-mode auth (Entra + iam), server-derived roles** | `AuthGate.tsx`, `lib/msal.ts`, `lib/config.ts` | No example does Entra/MSAL or dual-mode; the AgentCore example uses Cognito |
| 2 | **Dynamic catalog-driven runtime** (one `HttpAgent` per DB-catalog agent, per-request auth forwarding) | `app/api/copilotkit/[[...path]]/route.ts` | Every example hardcodes a single `default` agent |
| 3 | **Workspace shell + thread history** | `workspace/WorkspaceShell.tsx`, `lib/threads.ts` | Not an app; no shell to inherit |
| 4 | **Admin catalog screen** (role-gated CRUD + AgentCore sync) | `admin/`, `AgentCatalogAdmin.tsx` | No equivalent |
| 5 | **EventInspector** (live AG-UI shared state) | `AgentChat.tsx` | Built on `useAgent`; upstream has a fuller *Inspector* we could adopt (see Q2) |
| 6 | **HITL tool set** (4 client-proxy + 1 interrupt) | `hitl/HumanInTheLoop.tsx` | Hooks are CopilotKit's; the *tool set* is ours |
| 7 | **Rich A2UI catalog** (Chart/Mermaid/Markdown/Html) | `a2ui/richCatalog.tsx` | `createCatalog` is CopilotKit's; the *catalog* is ours (upstream `banking`/`pdf-analyst` examples mirror the idiom) |
| 8 | **A2UI preview page** (offline render-path proof) | `app/a2ui-preview/page.tsx` | Ours |
| 9 | **Generic agents home + fallback renderer** | `app/page.tsx`, `AgentChat.tsx` | Ours |

*~2,000 lines across ~14 files. Everything else (chat surface, streaming, tool
rendering, A2UI renderer, HITL plumbing) is **already** CopilotKit's.* These 9
encode architecture invariants 1–3, 5 — they are the platform's differentiated
value.

---

## Q2 — Features we could adopt (ranked by value ÷ effort)

All verified to exist in the pinned 1.62.3 (`@copilotkit/react-core/v2` type defs)
and to work with our **self-hosted runtime + remote AG-UI agents** setup.

### 🟢 Adopt now — free, in-place, low effort (we're already on the same provider+version)

| Feature | Hook / package | What it buys | Works with our proxy+AgentCore? | Effort |
|---|---|---|---|---|
| **CopilotKit Inspector** | `CopilotKitInspector` / `@copilotkit/web-inspector` | A full debug inspector web component — richer than our ~40-line `EventInspector` | ✅ reads the same `CopilotKitCore` | **S** (~0.5 d) |
| **Suggestions** | `useConfigureSuggestions` / `useSuggestions` | Clickable prompt suggestions per agent (seed instructions from the catalog `description`) | ✅ client-side | **S** (~0.5–1 d) |
| **`useFrontendTool`** ⭐ | `useFrontendTool` | Agent triggers **browser-side actions** (navigate to a ticket, open a file, highlight a diff, prefill a form). High value for an SDLC platform | ✅ tool defs flow through the runtime to the agent | **S–M** |
| **Attachments** | `useAttachments` | File/image inputs in the composer (attach a log, a screenshot, a spec) | ✅ client-side; agent must accept them | **M** |
| **Chat layout variants** | `CopilotSidebar` / `CopilotPopup` (v2) | Overlay/"copilot-over-a-canvas" UX instead of full-page chat — a rendering-mode change only | ✅ same provider | **S** |

### 🟡 Adopt deliberately — useful, but a real integration or product decision

| Feature | Hook / package | What it buys | Caveat | Effort |
|---|---|---|---|---|
| **MCP Apps (open-ended UI)** | MCP-apps middleware | The agent launches whole external apps (e.g. Excalidraw) — the "Open-Ended" gen-UI type | New trust/permissions surface; pairs with a `render_mode=plain`/open-ended path | **M** |
| **Voice** | `@copilotkit/voice` | Transcription + TTS in chat | Accessibility/UX nicety; not core to SDLC | **M** |
| **Channels (ChatOps)** | `@copilotkit/channels-slack` / `-teams` / `-discord` | Surface the same agents in **Slack / Teams** — very relevant for an enterprise SDLC workflow | Separate adapter + auth per platform | **L** |
| **`useComponent`** | `useComponent` | Register a **frontend-owned** React component as an agent tool (alt to `useRenderTool`) | Directly useful when wiring the `render_mode=static` path (deck Part 7) | **S** |

### 🔴 Defer — license-gated (CopilotKit Cloud / Intelligence) or governance-sensitive

| Feature | Hook / package | Why defer |
|---|---|---|
| **Server-persisted threads** | `useThreads` + `CopilotThreadsDrawer` + `@copilotkit/web-components` | **License-gated** (source shows a two-pronged license check; thread fetch is skipped while unlicensed). Threads live on the CopilotKit **Intelligence** platform (Cloud) via `CopilotKitIntelligence` + `licenseToken` + `identifyUser`. Our `localStorage` threads are the zero-cost, in-boundary alternative for Phase 0 |
| **Memory / learning** | `useMemories`, `useLearnFromUserAction` | Same Cloud dependency; puts conversation data in a third-party SaaS — a governance decision for a platform whose point is staying inside the AWS/enterprise-gateway boundary |
| **`sqlite-runner` / `agentcore-runner`** | backend runners | Backend concern — see `COPILOTKIT-NATIVE-MIGRATION.md`; `agentcore-runner` is **OSS** (no license) and fixes the AgentCore memory-replay risk |

---

## Q3 — If we wanted more of CopilotKit's UI while keeping our features: the path

There are two concrete interpretations. One is recommended; one is not.

### Path A (recommended) — stay, adopt more prebuilt v2 pieces *in place*

Because we're already on the same provider **and** version, this is additive — **nothing ports because nothing moves:**

1. **Swap `EventInspector` → `CopilotKitInspector`** — `npm i @copilotkit/web-inspector`, mount behind the same "Inspect state" toggle in `AgentChat.tsx`. Keep our shared-state JSON pane if the inspector doesn't show it. *~0.5 d, nothing breaks.*
2. **Enable free `CopilotChat` capabilities** — `useConfigureSuggestions` per agent (seed from the catalog `description`), `useFrontendTool` for browser-side actions, `useAttachments` if agents need file input. *~0.5–1 d each.*
3. **(Optional) `CopilotSidebar`** for a future canvas/workspace UX — a rendering-mode change; `AuthGate`, runtime route, HITL, `richCatalog` all untouched.
4. **(Deferred) CopilotKit Intelligence license** → replace `lib/threads.ts` + our history sidebar with `CopilotThreadsDrawer`, wiring `identifyUser` from the Entra-derived `/api/me` identity — only after a data-governance review.

**Total for items 1–2: ~1–2 days. All 9 custom features stay where they are.**

### Path B (NOT recommended) — adopt an example app as the scaffold

Using `examples/integrations/agentcore/` (or `strands-python`, or the `v2/react/demo`) as the base:

- **Ports unchanged** (pure library-consuming code): `richCatalog.tsx`, `A2UISurfaceView.tsx`, `HumanInTheLoop.tsx`, `lib/threads.ts` (~700 lines survive).
- **Full rework required:**
  - `AuthGate.tsx`/`msal.ts` — the example is **Cognito**; re-implement MSAL/Entra + `iam` mode inside its provider (~2–3 d; **breaks invariant 3** until done).
  - `api/copilotkit/[[...path]]/route.ts` — **breaks entirely** (Vite has no server routes; the example's runtime is a Lambda bridge with one hardcoded agent). Re-implement dynamic catalog registration + per-request auth forwarding (~3–4 d; **breaks invariant 2**).
  - A2UI middleware config — the example sets `injectA2UITool: false`; re-create our per-agent enablement (~1 d; **breaks invariant 5**).
  - `WorkspaceShell`, agents home (runtime scan), `admin/*` — no equivalents; rewrite (~4–5 d).
- **Also lost:** the Next.js 16 target (our frontend `AGENTS.md` requirement), and time re-verifying all 5 HITL contracts + A2UI paths live.

**Estimated cost: ~2–3 engineer-weeks to return to *today's* feature parity, with
zero end-user-visible gain and three invariants (2, 3, 5) violated mid-flight.**

---

## Recommendation (for an engineering manager)

**Stay on our frontend; adopt more prebuilt CopilotKit v2 components in place (Path
A). Do not adopt `CopilotKit-main` or its examples as a UI scaffold.**

Reasoning:

1. **The premise of "switch to CopilotKit's UI" is mostly already satisfied** — our
   chat surface, streaming, tool rendering, A2UI renderer, and HITL machinery are
   CopilotKit's own v2 components at the latest version. The monorepo is the *source
   of the packages we run*, not an alternative product.
2. **Everything we hand-built is exactly what CopilotKit doesn't ship** — Entra/iam
   dual auth with server-side roles, a DB/AgentCore-driven dynamic multi-agent
   runtime with per-request auth forwarding, an admin catalog, and a generic rich
   A2UI catalog. These encode our invariants; a scaffold swap deletes them, then
   makes us rebuild them (~2–3 weeks, negative value).
3. **The genuinely attractive pieces are adoptable in-place at trivial cost**
   (Inspector, suggestions, `useFrontendTool`, sidebar mode) — the payoff of having
   built *on* the library rather than beside it.
4. **The only structural upgrade CopilotKit offers — persisted threads/memory — is a
   paid Cloud (Intelligence) feature** that puts a third-party SaaS in the data path
   of a deployment designed to stay inside the AWS/enterprise-gateway boundary.
   Revisit as procurement + governance, not engineering.

**Concrete next steps:** (a) adopt `CopilotKitInspector` + `useConfigureSuggestions`
this sprint; (b) prototype `useFrontendTool` for one SDLC action (e.g. "open this
ticket"); (c) keep `CopilotKit-main` as the reference checkout it already is — for
reading v2 source when docs lag, and for the CDK/Terraform in
`examples/integrations/agentcore/` when Phase 1 needs real IaC; (d) route the
`agentcore-runner`/threads decisions through `COPILOTKIT-NATIVE-MIGRATION.md`.

---

## Evidence

- CopilotKit monorepo: `package.json` (private nx/pnpm workspace, 1.62.3),
  `packages/react-core/src/v2/`, `packages/{a2ui-renderer,agentcore-runner,sqlite-runner,web-inspector,web-components,voice,channels-*}/`,
  `examples/integrations/{agentcore,strands-python}/`, `examples/showcases/{banking,a2ui-pdf-analyst,generative-ui-playground}/`, `sdk-python/copilotkit/`.
- Our frontend: `Phase0/frontend/package.json` (pins 1.62.3), `src/components/AgentChat.tsx`,
  `src/app/api/copilotkit/[[...path]]/route.ts`, `src/components/a2ui/richCatalog.tsx`,
  `src/components/hitl/HumanInTheLoop.tsx`, `src/components/AuthGate.tsx`, `src/lib/threads.ts`.
- Verified hook surface (`@copilotkit/react-core/v2`): `useAgent`, `useRenderTool`,
  `useRenderToolCall`, `useDefaultRenderTool`, `useComponent`, `useFrontendTool`,
  `useHumanInTheLoop`, `useInterrupt`, `useConfigureSuggestions`, `useSuggestions`,
  `useThreads`, `useAttachments`, `useMemories`, `useLearnFromUserAction`,
  `useCapabilities`, `useCopilotKit`.
