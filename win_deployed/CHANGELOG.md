# Changelog — enterprise delivery package

All notable changes to the enterprise package staged in `win_deployed/` are
documented here. This versions **what we hand to the enterprise environment**,
not the application itself.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Bump `VERSION` and add an entry here whenever the payload changes. See
`README.md` for the delivery workflow.

## [Unreleased]

_Nothing yet._

## [1.8.0] — 2026-07-17

### Fixed

- **Every `draft_*` form rendered blank.** The press-release and bug-report cards
  showed empty Headline / Body / Contact fields while the agent had streamed a
  complete draft.

  `args` **arrives empty and fills in over time**: CopilotKit renders the card as
  soon as `TOOL_CALL_START` lands, then the agent streams the arguments in as
  `TOOL_CALL_ARGS` deltas — a few characters per event. `EditableForm` seeded its
  fields with `useState(() => …args…)`, whose initializer runs **once**, on that
  first empty render. The values never caught up.

  Proven from the live stream rather than guessed:

  ```
  TOOL_CALL_START  draft_press_release
  TOOL_CALL_ARGS   delta: "{\"headline\":"
  TOOL_CALL_ARGS   delta: " \"Phase 0"
  TOOL_CALL_ARGS   delta: " Launches t"
  ```

  The form now mirrors `args` as it streams and stops once the user types in a
  field, so an edit is never clobbered by a later delta.

  **Why it looked agent-specific:** `ApprovalCard` and `ChoiceCard` read `args`
  directly in render, so they re-render as deltas land and always worked. Only the
  two cards that copied args into state were broken — `draft_press_release` and
  `draft_bug_report`.

  This is the second bug in two days from the frontend mis-reading streamed data
  (1.7.0 was the interrupt value arriving as a JSON string). Both were invisible to
  `smoke_test.py`, which asserts on the decoded stream rather than on what the
  browser renders.

### Added

- **`deploy_agent.py --runtime=<name-or-arn>`** — update an existing runtime whose
  name the script would not guess.

  Without it the script only finds runtimes **it** created, because it derives the
  name from the agent directory (`a2ui-demo-strands` → `a2ui_demo_strands`). A
  runtime created by hand in the console carries whatever name the operator typed,
  so the guess misses and the script **silently creates a second runtime** —
  leaving the original live and the catalog holding both. Four of the five runtimes
  in the personal account are named `Planner` / `Release_Readiness` /
  `Press_Release` / `A2UI_demo`, so a plain redeploy there would have produced four
  duplicates. It matters for the enterprise too: deploys there are manual via the
  console.

The five AgentCore packages are **byte-identical to 1.7.0** — git records all five
as 100% renames. These are a frontend fix and a deploy-script flag; only
`agui-frontend` and `agui-agents` changed content.

## [1.7.0] — 2026-07-16

### Fixed

- **The release Go/No-Go card rendered blank.** In the enterprise UI the card
  appeared with an empty *"Recommendation:"* and no reasons — while the agent had
  sent both.

  `HumanInTheLoop.tsx` read the LangGraph interrupt as
  `event.value as { tool, recommendation, reasons }`. That is a **compile-time
  cast over a runtime string**: `ag-ui-langgraph` emits the interrupt as a CUSTOM
  `on_interrupt` event whose `value` is **JSON-encoded as a string** (the decoded
  object sits under `rawEvent.value`). Every field read came back `undefined`, so
  the card rendered with nothing in it. The `v.tool` guard also read `undefined`,
  which is why the card still appeared instead of being filtered out — the bug hid
  itself.

  The value is now parsed (objects still accepted, malformed JSON degrades to an
  empty card rather than throwing).

  Captured from a live local run — the payload was never the problem:

  ```
  "value":"{\"tool\": \"request_go_nogo\", \"recommendation\": \"no-go\",
            \"reasons\": [\"Test coverage: 78 percent, target is 80 percent\", ...]}"
  ```

  **Why no test caught it:** `scripts/smoke_test.py` decodes the same string
  (`if isinstance(raw, str): json.loads(raw)`) and asserts on the decoded value, so
  it passed while the UI was blank. The Python client was defensive and the
  TypeScript client was not — the same shape as the port bug, where the test
  covered exactly the paths that worked.

The deployable AgentCore packages are **byte-identical to 1.6.0** — git records all
five as 100% renames, which the lock from 1.5.0 is what makes possible. This is a
frontend fix; only `agui-frontend` changed content (97% similar).

## [1.6.0] — 2026-07-16

### Added

- **`agents/scripts/invoke_agentcore.py`** — test a deployed AGUI runtime straight
  against AgentCore, with no backend running. It answers the question you have
  right after uploading a zip: *did that upload work?* — before you've stood up the
  backend, the DB or the frontend.

  An AGUI runtime can't be checked with the console's plain "Test" panel the way a
  normal agent can. It doesn't take a prompt and return JSON; it speaks the AG-UI
  protocol — `POST /invocations` takes a **RunAgentInput** object and streams back
  Server-Sent Events. The console shows raw bytes. This script builds the
  RunAgentInput, SigV4-signs an `InvokeAgentRuntime` call, and renders the event
  stream (`RUN_STARTED`, text deltas, `TOOL_CALL_START`, `RUN_ERROR`,
  `RUN_FINISHED`). Exit 0 = booted and streamed; a `RUN_ERROR` naming an
  initialization timeout points at wrong port / missing `BEDROCK_*` and the
  `[runtime-logs]` stream. Needs only `AWS_REGION` and AWS credentials.

  This fills the gap below `smoke_test.py`: S0 tests the whole stack through the
  backend (catalog → proxy → SigV4) and needs it running; this tests one runtime
  directly. The agents README now documents all three tiers — direct probe, S0,
  interactive UI.

  The SSE renderer was verified against a real agent booted locally (RUN_STARTED →
  RUN_FINISHED over a live `/invocations` stream) and its error/tool-call branches
  against synthetic streams. The `InvokeAgentRuntime` + SigV4 wrapper itself could
  not be exercised from here — it needs a real AgentCore runtime, which lives
  inside the enterprise.

The deployable AgentCore packages are **byte-identical to 1.5.0** (proven by
hash — the lock makes this checkable now): the new script is tooling under
`scripts/`, not agent code, so nothing that gets uploaded changed. Only the
filenames moved 1.5.0 → 1.6.0.

## [1.5.0] — 2026-07-16

### Added — the delivered bytes are now actually reproducible

- **Every agent carries a `requirements.lock`** and `build_zip.sh` installs from
  it. `requirements.txt` pins only the direct dependencies — **6 of the 54
  packages** that end up in a zip. The other 48 were resolved fresh against live
  PyPI on every build, so a rebuild changed what shipped on its own: `langsmith`
  0.10.4 → 0.10.5 (1.2.0), then `botocore` 1.43.48 → 1.43.49 across all five
  (1.4.0). Both were found by comparing zips afterwards. Neither was reviewed.

  **The gain is visibility more than determinism.** With a lock, those bumps are a
  one-line diff in `requirements.lock` that someone approves before it ships.

  Verified: two consecutive builds from unchanged sources are now
  **byte-identical**. `README.md`'s reproducibility claim is finally true without
  a caveat, and a checksum mismatch against `agentcore/SHA256SUMS.txt` means
  something again.

- **The lock is mandatory.** `build_zip.sh` refuses to build without one, and
  refuses if `requirements.txt` is newer than the lock. There is deliberately no
  fall back to `requirements.txt`: a silent fallback to an unpinned resolution is
  the failure this removes. Regenerate with `Phase0/scripts/lock_agents.sh`.

### Unchanged

**The lock changed nothing about what ships.** It captured the resolution 1.4.0
was already using — a package-by-package comparison of 1.4.0 vs 1.5.0 shows no
version differences. It froze the current state rather than moving it.

The lock is a build input, not a runtime file: it is not inside the deployable
zips (`build_zip.sh` copies only `*.py`), but it does travel in
`agui-agents-<VERSION>.zip` so this side can rebuild identically.

## [1.4.0] — 2026-07-16

### Changed

- **The deployable packages now carry the version in their filename**:
  `dist/agentcore/<agent>-1.4.0.zip`, was `<agent>.zip`. A package on disk, or one
  already uploaded to a runtime, can now be identified without unzipping it. The
  rename costs nothing in git — an unchanged package keeps its content hash, so a
  version bump is a tree entry, not another 151 MB of blobs.

- **`make_agentcore_zips.sh` now produces them.** Staging these was a hand-run
  `build_zip.sh` + `cp` + `shasum` sequence documented in the README with nothing
  enforcing it — and `make_zips.sh` deleted `dist/agentcore/` on every run while
  only recreating the three source zips. The gap was invisible, because `dist/`
  still looked populated afterwards. `make_zips.sh` now removes only its own
  `agui-*.zip`; `dist/agentcore/` has an owner.

### Dependency drift picked up by this rebuild

- **`botocore` 1.43.48 → 1.43.49, in all five packages.** Nothing of ours changed;
  the rebuild resolved a newer transitive dependency. `boto3` is pinned at
  `1.43.46` and stayed there — `botocore` is *its* dependency and is not pinned by
  anything.

  This is the second such drift in two days (`langsmith` 0.10.4 → 0.10.5 in 1.2.0),
  and this one moved **every** package rather than one. The rebuild was verified:
  all five still carry the current agent sources byte-for-byte, the gateway-only
  factory, zero Bedrock fallback and port 8080. But it is now demonstrated, not
  theoretical, that a rebuild changes the delivered bytes on its own — pinning the
  full resolution (a lock file, or `uv --exclude-newer`) is the fix and is still
  not done.

## [1.3.0] — 2026-07-16

### Added

- **`agents/scripts/smoke_test.py` now ships**, and its new **S0** check probes
  **every** agent in the catalog — not a hand-picked pair.

  S0 exists because of how the port bug reached this package: `smoke_test.py`
  exercised only `planner` and `release`, both of which happened to bind 8080, so
  five green checks coexisted with two undeployable agents. S0 asks the catalog
  (`GET /api/agents`) which agents are registered and probes each one, so an agent
  added later is covered without editing the test. No ids are hardcoded.

  **The probe is an invoke, deliberately.** The control plane reports a runtime
  `READY` whether or not its container can boot — the port bug sat behind a READY
  runtime. Only an invoke reveals it. To keep that cheap, S0 stops at the first
  `RUN_STARTED`, which AG-UI emits *before* the model is called: it proves catalog
  → proxy → SigV4 → AgentCore → container booted → agent running, for roughly no
  tokens. S1–S5 still exercise `planner` and `release` in depth.

  When a runtime fails, S0 translates AgentCore's *"initialization time
  exceeded"* into the three things actually worth checking — wrong port, a missing
  `BEDROCK_ENDPOINT_URL` / `BEDROCK_API_KEY` / `BEDROCK_MODEL_ID`, and the
  `[runtime-logs]` stream where the real traceback is. Those causes are
  indistinguishable from the outside, which is why the message names all of them.

  It ships because it can only run where the backend and the runtimes are
  reachable, which is inside the enterprise. It reads `agents/.env` for
  `BACKEND_URL` (default `http://localhost:8000`) and `AUTH_MODE`; in `entra` mode
  export `SMOKE_BEARER_TOKEN` first.

### Changed

- Removed an internal planning-note block from `smoke_test.py` before shipping it
  (a stale `[Human]` to-do list referencing our own docs). 1.0.0 cleaned this class
  of reference out of the payload; shipping this file would have reintroduced it.

The built AgentCore packages are **byte-identical to 1.2.1** — `smoke_test.py`
lives in `scripts/`, not in an agent directory, so no deployable package changes.

## [1.2.1] — 2026-07-15

### Fixed — the rest of the documentation the fork made false

1.2.0 fixed the false statements it happened to look at. An adversarial re-audit
found 20 more across 14 files. No code behaviour changes here; the shipped agent
sources and the built AgentCore packages are **byte-identical to 1.2.0**.

Worst first — these were not stale prose, they were instructions that cause damage:

- **`.agents/rules/`** — the always-on rules every agentic tool reads before it
  touches anything — still taught the deleted env-driven switch, and
  `00-start-here.md` said *"Never fork or duplicate app code into `cloud_deploy/`"*.
  That instructs the next agent to **undo the fork**. `10-invariants.md` 4 and 7,
  `40-aws.md` and `00-start-here.md` now match `AGENTS.md`.
- **`cloud_deploy/README.md`** described any `agents/` there as an untracked local
  artifact, *"safe to delete"*. It is the tracked enterprise fork — following that
  deletes the gateway-only build. Also added `agents/` and `scripts/` to its
  "What's here", which listed only `env/`.
- **`agents/README.md`** (shipped, and the deploy mechanism, since deploys are
  manual): seven surviving contradictions. `BEDROCK_MODEL_ID` was "Recommended …
  defaults to Claude Haiku 4.5"; the troubleshooting table blamed a
  *"fell back to Bedrock SigV4"* cause that **cannot occur in this build** and
  would send the operator hunting the wrong bug; `AWS_REGION` was described as the
  SigV4 scope when `model_factory.py` never reads it.
- **`README.md`** claimed *"There is no fork"*, said `dist/` is git-ignored two
  sections after explaining why it is tracked, and reported VERSION as 1.0.0.
- **`scripts/deploy_agent.py`** printed `"Gateway mode: …"` — announcing a mode
  that no longer exists in either build.
- **`scripts/build_zip.sh`**'s header promised byte-identical rebuilds with no
  mention of the transitive-dependency caveat that 1.2.0 hit.
- Dead `LOCAL_AGENT_URL_*` "run an agent locally against the backend" instructions
  removed from `AGENTS.md`, `Phase0/README.md` and both `run` workflows — the
  proxy has had no local override for some time, so they silently did nothing.

**Why they went stale:** hand-written enterprise files have no `Phase0/`
counterpart, so `check_sync.sh` excludes them by design and they fail silently.
`.agents/rules/` is outside every gate. Both remain uncovered — re-read them by
hand whenever the config surface moves.

## [1.2.0] — 2026-07-15

### Fixed

- **Tracing was probably disabled on AgentCore, by us.** `a2ui-demo-strands` and
  `press-release-strands` decided whether to switch OpenTelemetry off by checking
  whether `OTEL_EXPORTER_OTLP_ENDPOINT` was set, on the assumption that the
  AgentCore runtime injects it. **No AWS documentation says it does** — for
  runtime-hosted agents the docs say observability is enabled automatically, and
  the opt-out is `DISABLE_ADOT_OBSERVABILITY`. If the variable is not injected,
  that check set `OTEL_SDK_DISABLED=true` on the runtime as well, turning off the
  tracing that feeds the `otel-rt-logs` stream and GenAI Observability.

  The guard is now keyed off an explicit **`LOCAL_DEV`** flag, which cannot be
  wrong about its own environment. It is set in `agents/.env` (never packaged
  into the zip), so it is present locally and absent on AgentCore. **Do not set
  `LOCAL_DEV` on a runtime.** It exists because Strands' span instrumentation
  crashes the local SSE stream; that is a local-only problem.

  Still **unverified**: whether AgentCore injects `OTEL_EXPORTER_OTLP_ENDPOINT`.
  This change makes the answer stop mattering.

### Changed — documentation that had gone false

The `1.1.0` fork removed the Bedrock fallback from the agents, but the
hand-written enterprise docs still described the old env-driven behaviour. They
are not covered by the drift check (they have no `Phase0/` counterpart), so they
went stale silently. Since deployment here is **manual via the AgentCore
Console**, these documents *are* the deployment mechanism:

- **`agents/.env.example`** claimed the agents "fall back to Amazon Bedrock via
  SigV4" if a variable was empty, and that `BEDROCK_MODEL_ID` "falls back to
  Claude Haiku 4.5". Both were untrue as of 1.1.0 — all three variables are
  mandatory and the agent raises without them. It now also states that a deployed
  agent never reads this file: the same values must be entered as runtime
  environment variables in the console.
- **`agents/README.md`** still listed `a2ui-demo-strands` on port 8090 and
  `press-release-strands` on 8091 — the exact bug fixed in 1.0.2. All five serve
  8080. Its "gateway mode ON/OFF" section was replaced with what the build
  actually does. **(1.2.0 replaced that one section only; seven further
  contradictions survived elsewhere in the same file and were fixed in 1.2.1 —
  this entry overstated the fix.)**
- **`README.md`** repeated "gateway mode activates when both … are set".

Also documented: what a missing variable actually looks like (an initialization
timeout, indistinguishable from a wrong port) and where the real error is (the
runtime's `[runtime-logs]` CloudWatch stream, not `otel-rt-logs`).

### Dependency drift picked up by this rebuild

- **`langsmith` 0.10.4 → 0.10.5** inside
  `dist/agentcore/release-readiness-langgraph.zip`. Nothing of ours changed in
  that agent; the rebuild resolved a newer transitive dependency published
  upstream since 1.1.0.

  This exposed an overstated claim in `README.md`: the built packages were
  described as reproducible full stop. They are reproducible **given the same
  resolved dependencies** — each `requirements.txt` pins only direct
  dependencies, so transitive ones float and a rebuild days later can differ
  through no change of ours. The README now says so, and notes that a checksum
  mismatch against `agentcore/SHA256SUMS.txt` is not by itself evidence of
  tampering. Fixing this properly needs a fully pinned resolution (a lock file,
  or `uv --exclude-newer`); that is not done yet.

## [1.1.0] — 2026-07-14

### Changed

- **The shipped agents can no longer call Amazon Bedrock — the code path is
  gone.** `agents/*/model_factory.py` now comes from the enterprise fork at
  `cloud_deploy/agents/` and talks only to the GenAI marketplace gateway. It
  requires `BEDROCK_ENDPOINT_URL` and `BEDROCK_API_KEY` and raises if either is
  missing.

  Previously one file served both environments and picked the provider from the
  environment: if either variable was empty it **silently** fell back to Amazon
  Bedrock over SigV4. On an account with no Bedrock model access that is at best
  a confusing failure and at worst enterprise traffic sent somewhere it must not
  go — and nothing in the logs said so. `scripts/deploy_agent.py` already carried
  a warning about this: AgentCore's `update_agent_runtime` replaces the whole
  environment map, so a redeploy could strip the gateway config from a running
  runtime and drop it back to Bedrock. That hazard no longer exists.

  **For the operator:** if `agents/.env` is filled in as documented, nothing
  changes. If the gateway is *not* configured, agents now fail loudly at startup
  instead of quietly trying Bedrock.

  Verified by DNS interception during a real `Converse` round-trip: with the
  gateway configured the process contacts `genaiapigwna.jnj.com` and nothing
  else; with it unset the agent refuses to build and contacts **no host at all**.
  The client region is also pinned to a non-routable placeholder (as in the
  marketplace's own code samples), so langchain's control-plane client can no
  longer resolve `bedrock.<region>.amazonaws.com`.

- **`ConverseStream` is still registered for the `x-api-key` header** alongside
  `Converse` and `CountTokens`, since `BEDROCK_STREAMING` defaults to on. The
  marketplace's published samples only demonstrate `Converse` and `InvokeModel`;
  if the gateway does not proxy `converse-stream`, set `BEDROCK_STREAMING=false`
  in `agents/.env` — the UI still streams, because AG-UI rebuilds the token
  stream locally.

## [1.0.2] — 2026-07-14

### Fixed

- **`press-release-strands` and `a2ui-demo-strands` were undeployable.** They
  bound `:8091` and `:8090`; AgentCore runs `agent.py` as the entrypoint and then
  probes `GET /ping` on **8080** (the contract in `ARCHITECTURE.md`, and the
  `AGUIApp.run` default). Nothing answered there, so the runtime never went
  healthy and every invoke failed with *"Runtime initialization time exceeded.
  Please make sure that initialization completes in 30s."* — a message that reads
  like a slow cold start but was really "the port was never opened" (the agent
  finishes initializing in ~1s).

  The two odd ports were local side-by-side dev ports, left over from when the
  proxy could be aimed at a local process via `LOCAL_AGENT_URL_*`. That mechanism
  no longer exists — `agui_proxy.py` resolves `runtime_arn` from the DB catalog
  and always SigV4s to AgentCore — so the ports only broke deployment. The three
  agents that already bound 8080 were unaffected, which is why this looked
  healthy: `smoke_test.py` covers only `planner` and `release`.

  This shipped inside `dist/agentcore/press-release-strands.zip` and
  `a2ui-demo-strands.zip` in 1.0.1, so **both built packages are rebuilt here**.
  The other three agents rebuild byte-identically (reproducible builds), so only
  the two fixed packages change.

## [1.0.1] — 2026-07-14

### Changed

- **`agents/scripts/build_zip.sh` now produces reproducible zips.** The same
  `requirements.txt` and sources always yield byte-identical output, verified by
  building all five agents twice from scratch and comparing checksums.

  Three sources of non-determinism were removed:
  - **Timestamps** — the zip format stores an mtime per entry, so every build
    embedded fresh pip install times. All packaged files are now stamped with a
    fixed `SOURCE_DATE` (`touch -h -t 202001010000`).
  - **Entry order** — `zip -r` took its order from filesystem traversal. The file
    list is now piped in sorted (`find | LC_ALL=C sort | zip -X -@`).
  - **Extra attributes** — `-X` drops uid/gid, atime and Finder metadata, which
    vary per machine.

  Bytecode caches (`__pycache__`, `*.pyc`) are also stripped: they embed build
  paths and are regenerated by Python at runtime.

  **Why it matters:** a rebuild that changes nothing now changes no bytes, so the
  built AgentCore packages can be version-controlled without adding ~151 MB of
  blobs per build. It also lets the enterprise side build the package itself and
  compare its checksum against ours to prove the artifacts match.

  No behaviour change to the packaged agents — same file counts, `agent.py` still
  at the zip root, every native binary still ARM64.

## [1.0.0] — 2026-07-14

Initial enterprise delivery package: three standalone, zip-delivered payloads
for a Windows 11 + WSL2 (Ubuntu) environment with no git access.

### Added

- **Three standalone payloads** — `backend/` (21 files), `frontend/` (34),
  `agents/` (23); 78 in total (66 code files copied verbatim from `Phase0/` plus
  12 hand-written enterprise files). Each is self-contained and intended to
  become its own Bitbucket repo on arrival. There is no fork of the code.
- **Gateway-ready agents** — all five AgentCore agents (`sdlc-planner-strands`,
  `release-readiness-langgraph`, `bug-report-strands`, `a2ui-demo-strands`,
  `press-release-strands`) collected under one `agents/` folder, together with
  `scripts/build_zip.sh` and `scripts/deploy_agent.py`. They route to the GenAI
  marketplace API gateway instead of Amazon Bedrock when both
  `BEDROCK_ENDPOINT_URL` and `BEDROCK_API_KEY` are set in `agents/.env`; the
  AgentCore deploy process is documented in `agents/README.md`.
- **Windows 11 + WSL2 operator READMEs** — a `README.md` per payload, written in
  English for an operator who did not build the app, covering prerequisites
  (nvm/Node 20+ LTS, uv/Python 3.13, AWS credentials in `~/.aws`), configuration,
  run commands, and the WSL gotchas: keep the code on the Linux filesystem rather
  than `/mnt/c`, unzip inside WSL, and `chmod +x` shell scripts after unzipping.
- **LF enforcement** — a `.gitattributes` per payload (`* text=auto eol=lf`,
  `*.sh text eol=lf`) so shell scripts committed to Bitbucket from Windows are
  not converted to CRLF and do not fail with `bad interpreter`.
- **Per-payload `.gitignore`** — each repo stands alone; the monorepo-root
  ignore rules do not travel with the zips.
- **Config templates** — `backend/.env.example`, `agents/.env.example`,
  `frontend/.env.local.example`, all with blanks. No real secret ships.
- **Staging tooling** (our side, not shipped) — `scripts/_payload.sh` as the
  single definition of what ships, `scripts/build_packages.sh` to re-sync from
  `Phase0/`, `scripts/check_sync.sh` for a read-only drift verdict against
  `Phase0/`, and `scripts/make_zips.sh` to produce
  `dist/agui-{backend,frontend,agents}-<VERSION>.zip` plus `SHA256SUMS.txt`.
- **`MANIFEST.sha256`** — sha256 of every shipped file, so we can prove and
  compare exactly what a given package version contained.

### Fixed

This package depends on upstream fixes in `Phase0/` (fixed at the source, then
re-synced, so the payload stays a verbatim copy), all required for the standalone
enterprise layout to behave correctly:

- **`frontend/next.config.ts` — `NEXT_PUBLIC_*` fallback.** Its `env: {}` block
  overrides `.env.local` for every key it lists. In the monorepo the repo-root
  `Phase0/.env` supplied the non-prefixed vars (`AUTH_MODE`, `BACKEND_URL`,
  `ENTRA_*`), but a standalone frontend repo has no parent `.env`, so those keys
  resolved empty and the app **silently booted with `AUTH_MODE=iam` — SSO off,
  all routes open**. The config now falls back
  (`process.env.AUTH_MODE ?? process.env.NEXT_PUBLIC_AUTH_MODE ?? "iam"`), making
  `frontend/.env.local` with `NEXT_PUBLIC_*` names the real config source in the
  enterprise repo. Verified by build test.
- **`scripts/deploy_agent.py` — environment variables are now merged.**
  AgentCore's `update_agent_runtime` **replaces** the `environmentVariables` map
  wholesale, so a redeploy silently wiped the gateway configuration from a
  running runtime. The script now merges onto the runtime's existing variables,
  and passes `BEDROCK_ENDPOINT_URL`, `BEDROCK_API_KEY`, and `BEDROCK_STREAMING`
  through when set.
- **`backend/` — Alembic now resolves `DATABASE_URL` the same way the app does.**
  Only `app/main.py` loaded the `.env` file, while `alembic/env.py` imports
  `app.db` directly — so `alembic upgrade head` never saw a `DATABASE_URL` set in
  `backend/.env` and would **silently migrate the local SQLite file while the app
  ran against Postgres**. Env loading moved into the shared `app/env_boot.py`,
  which both entry points now call. Verified: with `DATABASE_URL` set only in
  `backend/.env`, the Alembic import path resolves that URL.
- **Shipped code no longer references internal documents.** Dangling citations to
  our planning docs were removed from `frontend/src/components/hitl/HumanInTheLoop.tsx`,
  `agents/sdlc-planner-strands/tools.py` and `scripts/deploy_agent.py`, and the
  stale `LOCAL_AGENT_URL_*` local-dev note (a feature no longer present in the
  proxy) was corrected in `agents/a2ui-demo-strands/agent.py`. Monorepo-only paths
  in `alembic.ini` and `app/db.py` comments were made layout-neutral.

### Excluded by design

- Our dev/agent tooling: `.claude/`, `.agents/`, `CLAUDE.md`, `AGENTS.md`.
- Internal and non-English docs: `Phase0/README.md`, `ARCHITECTURE.md`,
  `SUNUM-AGUI-A2UI.md`, `VERSIONS.md`, `docs/`, audit and plan documents.
- Secrets: every real `.env`. Only `*.example` templates ship.
- Build artifacts and local state: `node_modules/`, `.venv/`, `.next/`,
  `build/`, `*.zip`, `*.pyc`, `*.db`, `*.sqlite3`, `*.tsbuildinfo`.
- Git history — delivery is by zip.
- Not needed to deploy and run: `cloud_deploy/`, `a2a-poc/`, `aws-setup/`.

### Known issues

- The hand-written enterprise files (READMEs, `.env` templates) have no
  `Phase0/` counterpart and are therefore not drift-checked; they must be
  reviewed by hand whenever the config surface changes.
- The GenAI marketplace gateway has not been exercised end to end from here:
  `BEDROCK_API_KEY` ships blank and the operator fills it. If the gateway does
  not proxy `converse-stream`, set `BEDROCK_STREAMING=false` (the UI still
  streams — AG-UI rebuilds the token stream locally).
- The backend's CORS origin is currently fixed to `http://localhost:3000`, which
  is fine for the local WSL run this package targets but must change if the
  frontend is ever served from another origin.

[Unreleased]: #unreleased
[1.0.0]: #100--2026-07-14
