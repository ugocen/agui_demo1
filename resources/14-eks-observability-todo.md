# EKS + CloudWatch Observability — TODO

Move `Phase0/backend` (FastAPI) and `Phase0/frontend` (Next.js 16) off local-run
and onto Amazon EKS via `kubectl`, with application logs and per-operation
("profiler") traces in CloudWatch.

This is the concrete, verified form of the observability slice that doc 13 lists
under Phase 1 ("EKS, RDS PostgreSQL, ... CloudWatch observability add-on plus
Transaction Search"). Researched against the repo as it stood on 2026-07-22 and
against current AWS docs.

**Status: parked.** Nothing here is applied. Five environment questions (§8) gate
the start; question 1 is a genuine fork in the design, not a detail.

Source material: `eks-observability-implementation-guide.md` (a generic brief).
This TODO **departs from it in three places** — see §3. Where they disagree,
this document is the one that was checked against the repo.

---

## 1. The headline

**Observability is the small half of this job.** The repo has never been
containerized and carries three assumptions that hold on a laptop and break on
EKS. Those are the critical path; instrumentation is comparatively easy and
partly already done.

| | Status |
|---|---|
| JSON structured logging | **Already built** — `LOG_FORMAT=json` in `logging_setup.py` |
| Dockerfiles / k8s manifests | **Do not exist** — nothing in the repo |
| Platform DB | **SQLite on local disk** — breaks on >1 replica and on every restart |
| AWS credentials for SigV4 | **Laptop `aws login` session** — must become IRSA/Pod Identity |
| Backend CORS origin | **Hardcoded** `http://localhost:3000` |
| Traces / spans | Not started |
| Browser telemetry | Not started |

Rough split: §4 (containerize + the three blockers) is ~60% of the work. §5–§6
(logs + backend/frontend server traces) deliver the "which command ran, how long
did it take" view that motivated this.

---

## 2. Current state — verified

The request path is **four tiers**, not the two the source guide assumes:

```
Browser (React 19)
  └─> Next.js server, route handler /api/copilotkit      [EKS pod, Node]
        └─> FastAPI /api/agui/{agent_id}                 [EKS pod, Python]
              └─> Bedrock AgentCore runtime              [AWS-managed, OUTSIDE EKS]
```

Tier 2 is absent from the guide entirely, and it is where the CopilotKit runtime
and the A2UI middleware live — real latency that is invisible from both the
browser and the backend.

Tier 4 runs outside the cluster. Its telemetry comes from AgentCore's own
observability. Traces will show the backend's outbound call as a client span and
stop there. **Cross-boundary agent tracing is out of scope** for this TODO;
verify separately.

### In our favour

* `Phase0/backend/app/logging_setup.py` wires structlog through the **stdlib**
  backend, so httpx/botocore render through the same JSON renderer.
  `LOG_FORMAT=json` + `LOG_LEVEL` are already env-driven — the guide's §B.2 is
  essentially implemented, minus trace-id injection.
* `Phase0/backend/app/main.py:53` already sets `allow_headers=["*"]`, satisfying
  the guide's §B.6 concern about `traceparent` / `tracestate`.
* Next.js is **already OpenTelemetry-instrumented internally** and emits spans
  for route handling, rendering, and every server-side `fetch`. Tier 2 needs an
  exporter registered, not hand-instrumentation.

### Blockers unrelated to observability

* [ ] **`Phase0/backend/app/db.py` defaults to SQLite** at `backend/phase0.db`.
      On EKS the agent catalog dies with the pod and diverges across replicas.
      `DATABASE_URL` is already honoured, so this is configuration, not code —
      point at RDS Postgres (`postgresql+asyncpg://…`), add `asyncpg` to
      `requirements.txt`. Until then the backend is **single-replica only**.
* [ ] **SigV4 credentials.** `agui_proxy.py:69` calls
      `boto3.Session().get_credentials()`. On EKS that must resolve through
      **IRSA or EKS Pod Identity**, with `bedrock-agentcore:InvokeAgentRuntime`
      plus the control-plane read actions the catalog sync needs. The existing
      503 path makes a misconfiguration easy to spot.
* [ ] **`main.py:55` hardcodes `allow_origins=["http://localhost:3000"]`.** Must
      become env-driven before anything works behind an ingress hostname.

---

## 3. Departures from the source guide

### 3.1 Application Signals instead of a self-managed ADOT Collector

The guide (§A.2) deploys an `OpenTelemetryCollector` CR, hand-writes its config,
creates a dedicated SA + IAM policy, and exposes port 4318 through a public
ingress. That was correct before the CloudWatch Observability add-on absorbed
the job.

The add-on now installs Fluent Bit **and** the CloudWatch agent **and** the
OpenTelemetry operator, and auto-instruments from a single pod annotation — the
ADOT SDK arrives via an init container, so **no OTEL packages are added to
`requirements.txt`** for the basic path.

Dropped: the Collector CR, its IAM role and policy, the OTLP ingress and its
CORS config, and the guide's §A.3 policy JSON.

Trade-off, stated plainly: less control over pipelines and processors than a
hand-written collector config. If custom processors are needed later (tail
sampling, attribute scrubbing, a second destination), run a collector alongside
then — but do not start there.

> ⚠️ Add-on **v5.0.0+ overrides OTLP exporter endpoints hardcoded in application
> code.** It does *not* override endpoints from container env vars or `envFrom`.
> **Always configure OTEL endpoints as env vars**, never as literals in
> `instrumentation.ts` or Python. This one rule prevents a whole class of
> "traces silently stopped after an add-on upgrade" incidents.

### 3.2 Do not use the pod annotation for the Next.js frontend

`instrumentation.opentelemetry.io/inject-nodejs: "true"` works via
`NODE_OPTIONS=--require`. AWS recommends **CommonJS** for Node
auto-instrumentation and calls ESM support experimental/limited. Next.js bundles
its own server code and ships an ESM-flavoured module graph in standalone
output — exactly where that injection is weakest.

**Use Next.js's own `instrumentation.ts` hook instead** (§6.2). It is the
officially supported path, it captures Next's *internal* spans (which `--require`
may miss because Next's modules are already bundled), and it is pinned by our
`package.json` rather than by an add-on upgrade.

Annotate the **backend** (`inject-python`); hand-wire the **frontend**.

### 3.3 CloudWatch RUM is likely the better browser answer

The guide (§C) sends browser OTLP through a **public ingress** — an
unauthenticated write endpoint on the internet, with abuse/cost risk and extra
CORS surface.

CloudWatch RUM is the native answer: app monitor, `enableXRay: true`,
`addXRayTraceIdHeader: true` to stitch sessions to server-side traces. Core Web
Vitals and JS error tracking come along for free; the OTEL browser SDK gives
neither.

Two real caveats:

* RUM propagates **`X-Amzn-Trace-Id`**, not W3C `traceparent`. Backend CORS must
  allow it (already covered) and the `xray` propagator must be in use.
* The web client loads from `client.rum.<region>.amazonaws.com` and needs a
  Cognito identity pool. **On a closed enterprise intranet this may be
  unreachable** — §8 question 1. If so, fall back to the guide's OTLP approach
  but put the collector ingress on an *internal* load balancer.

---

## 4. Phase 0 — Containerize and clear the blockers

Nothing below this section matters until this is done.

* [ ] **Backend image.** `python:3.13-slim`, install `requirements.txt`, copy
      `app/` + `alembic/`, `CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]`.
      Keep **one uvicorn worker** unless the pre-fork fix in §6.1 is applied —
      scale with pod replicas instead, which is Kubernetes-native anyway and
      sidesteps the OTEL fork problem entirely.
* [ ] **Frontend image.** Add `output: "standalone"` to `next.config.ts`;
      multi-stage `node:22-alpine` build; run `node server.js`.
      `.next/standalone` does **not** include `public` or `.next/static` —
      copying both is required, not optional.
* [ ] **Resolve the build-time env trap** (below).
* [ ] **DB:** provision RDS Postgres, set `DATABASE_URL`, add `asyncpg`, run
      `alembic upgrade head` as a k8s `Job` — *not* at pod startup, or concurrent
      replicas race.
* [ ] **IRSA:** service account + role trust policy; grant
      `bedrock-agentcore:InvokeAgentRuntime` plus the control-plane reads
      `agents_catalog.py` uses; annotate the backend ServiceAccount.
* [ ] **CORS:** replace the hardcoded origin in `main.py:55` with an env-driven
      list.

> ⚠️ **The build-time env trap.** `next.config.ts` declares an `env` block, and
> keys listed there are **inlined at `next build` time and override
> `.env.local` at runtime** — already documented in that file as load-bearing for
> SSO. So `NEXT_PUBLIC_BACKEND_URL`, the RUM app-monitor id, and any browser-side
> OTLP URL get **baked into the image**: one image cannot serve dev, test and
> prod.
>
> * **(a)** One image per environment, values as build args. Simple, honest about
>   what Next.js actually does.
> * **(b)** Serve runtime config from the server (a small route, or
>   `window.__RUNTIME_CONFIG__` injected from the root layout). One image, all
>   environments.
>
> Recommend **(b)** beyond a single environment — but it is a real code change to
> `AuthGate`/`config.ts`, not a config tweak. Decided by §8 question 5.

---

## 5. Phase 1 — Logs to CloudWatch

* [ ] **Install the add-on.**

      ```bash
      aws eks create-addon \
        --cluster-name <cluster-name> \
        --addon-name amazon-cloudwatch-observability \
        --region <region>
      ```

      Its service account needs `CloudWatchAgentServerPolicy` and
      `AWSXRayWriteOnlyAccess`. Prefer a dedicated IRSA role over
      inherit-from-node, so node roles stay minimal.

      Container stdout lands in **`/aws/containerinsights/<cluster-name>/application`**
      (confirmed current). No app-side AWS credentials involved.

* [ ] **Turn on JSON logging** — config only, both deployments:

      ```yaml
      env:
        - name: LOG_FORMAT
          value: "json"
        - name: LOG_LEVEL
          value: "INFO"      # raise to DEBUG per-deployment while investigating
      ```

      That is the entire backend logging change. ⚠️ The repo default is
      `LOG_LEVEL=DEBUG` — **set `INFO` explicitly** or you ship DEBUG to
      CloudWatch continuously and pay for it.

* [ ] **Add trace-id injection** — the one genuine code change. A processor in
      `_SHARED_PROCESSORS` (`logging_setup.py`), inserted before
      `format_exc_info`, reading `trace.get_current_span().get_span_context()`
      and emitting `trace_id` / `span_id`. Guard the import so the backend still
      runs locally without OTEL installed.

      > ⚠️ **X-Ray trace ids are not raw OTEL trace ids.** To jump from a log
      > line to a trace, format as `1-{first 8 hex}-{remaining 24 hex}`. Log both,
      > or log the X-Ray form — otherwise §7's correlation step fails and it looks
      > like traces are missing when they are not.

---

## 6. Phase 2 — Traces

### 6.1 Backend (Application Signals)

* [ ] Enable Application Signals account-wide, and **enable Transaction Search**
      — required for spans to reach the X-Ray OTLP endpoint. It switches span
      ingestion to a CloudWatch Logs destination and indexes 1% of spans free.
* [ ] Annotate the backend deployment's pod template:

      ```yaml
      annotations:
        instrumentation.opentelemetry.io/inject-python: "true"
      ```

      The add-on injects the ADOT Python SDK; FastAPI, httpx, boto3 and
      SQLAlchemy are auto-instrumented, covering the proxy hop, the AgentCore
      call and every DB query.

* [ ] **Add manual spans** where the "profiler" goal actually needs them:
      `agui_proxy.sigv4_headers` (credential resolution, a known failure point),
      the `catalog_service` AgentCore sync, and the `auth.py` Graph
      group-membership lookup — a network call on every request in entra mode,
      and the most likely hidden latency in the system.

> ⚠️ **Pre-fork servers break OTEL Python.** With >1 uvicorn/gunicorn worker the
> SDK's background threads do not survive the fork and workers export nothing,
> silently. Either keep one worker per pod (recommended) or put
> `from opentelemetry.instrumentation.auto_instrumentation import initialize;
> initialize()` at the top of `main.py` **before** the FastAPI import — which
> interacts with the existing `load_env()`-must-run-first ordering at
> `main.py:7`. Sequence carefully and verify both still work.

> ⚠️ **Highest-risk item in this TODO — verify SSE is not buffered.**
> Architecture invariant 1 says the AG-UI SSE stream must never be buffered.
> OTEL's ASGI instrumentation wraps the response and ends the server span when
> the final body message is sent; there are known upstream bugs in this area for
> SSE in sibling instrumentations.
>
> **Spike before rollout:** instrument one backend pod, open an agent chat,
> confirm tokens still arrive incrementally rather than in one burst.
>
> If it buffers, exclude the route via `OTEL_PYTHON_EXCLUDED_URLS="api/agui/.*"`
> and hand-instrument around the streaming call. Losing spans on one route is
> acceptable; breaking streaming is not.

### 6.2 Frontend server, tier 2

Do **not** annotate this deployment (§3.2).

* [ ] `npm install @vercel/otel @opentelemetry/api @opentelemetry/sdk-logs @opentelemetry/api-logs @opentelemetry/instrumentation`
* [ ] `Phase0/frontend/src/instrumentation.ts` exporting `register()` that calls
      `registerOTel({ serviceName: process.env.OTEL_SERVICE_NAME ?? "agui-frontend" })`.

      Per `Phase0/frontend/AGENTS.md`, read
      `node_modules/next/dist/docs/01-app/02-guides/open-telemetry.md` first — it
      is the version-correct reference and it is vendored in the repo.

* [ ] Endpoint via **env vars only** (§3.1), pointing at the add-on's agent:

      ```yaml
      env:
        - name: OTEL_SERVICE_NAME
          value: "agui-frontend"
        - name: OTEL_EXPORTER_OTLP_PROTOCOL
          value: "http/protobuf"
        - name: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
          value: "http://cloudwatch-agent.amazon-cloudwatch:4316/v1/traces"
        - name: OTEL_PROPAGATORS
          value: "tracecontext,baggage,xray"
      ```

**This is the payoff for the "profiler" requirement on the frontend.** Next.js
emits spans automatically for `[http.method] [next.route]` (request root),
`executing api route (app) /api/copilotkit/[[...path]]` (the CopilotKit runtime),
and `fetch [http.method] [http.url]` — **every server-side fetch**, including the
catalog read and each `HttpAgent` call to the backend.

Since `route.ts` re-reads `/api/agents` on every request by design (so `/admin`
`ui_mode` flips take effect), that per-request cost becomes visible immediately.
Expect it to be the first thing the trace view flags.

`NEXT_OTEL_VERBOSE=1` for the full span set while tuning; off normally.
`NEXT_OTEL_FETCH_DISABLED=1` kills fetch spans if they prove noisy.

### 6.3 Browser, tier 1

**Recommended: CloudWatch RUM**, subject to §8 question 1.

* [ ] App monitor with `enableXRay: true`, web client
      `telemetries: ['errors','performance',['http',{ addXRayTraceIdHeader: true }]]`.
* [ ] Wire through `Phase0/frontend/src/instrumentation-client.ts` — a Next.js
      file convention (v15.3+) that runs after document load and **before React
      hydration**, strictly better than the guide's "import at the top of the app
      entry". It also exports `onRouterTransitionStart`, giving client-side
      navigation timing for free. Keep it light: Next.js warns above 16ms init.
* [ ] **Frontend logs** — the guide's §C.3 advice stands: a small backend POST
      endpoint re-emitting browser events through structlog, so browser errors
      land in the same log group with the same trace id and there is no second
      ingestion path.

> ⚠️ `addXRayTraceIdHeader` **breaks SigV4-signed requests** and can break CORS.
> Our browser talks only to the Next.js server (same origin) and the backend —
> neither SigV4-signed from the browser — so this should be safe. Confirm against
> the `AuthGate`/MSAL token calls first, and test outside prod.

---

## 7. Phase 3 — The "profiler" layer, cost controls, verification

### 7.1 Profiler, in increasing depth

1. [ ] **Spans (§6)** — the actual answer to "what ran and how long".
       Application Signals gives per-operation latency/error dashboards and a
       service map with no further work. Start here; it answers most questions.
2. [ ] **Dynamic Instrumentation** — CloudWatch's live breakpoint/snapshot
       feature: capture variable state in a running pod **without redeploying**,
       the closest thing to an interactive profiler. Python supported. Needs
       `OTEL_AWS_DYNAMIC_INSTRUMENTATION_ENABLED=true`, `OTEL_SERVICE_NAME`, and
       `OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=<env>`, with the
       add-on at its latest version.
3. [ ] **CPU flame graphs** — for "where does time go *inside* a hot function",
       spans are the wrong instrument. `kubectl exec -it <pod> -- py-spy top --pid 1`,
       on demand. Needs `SYS_PTRACE` or a shared process namespace. Do not run
       continuous profiling until something justifies it.

The guide's §B.3 `timed()` decorator is redundant once spans exist — a span
already records duration, in a form you can aggregate and correlate. Skip it.

### 7.2 Cost controls — do not skip

* [ ] `LOG_LEVEL=INFO` normally; the repo default is DEBUG, override explicitly.
* [ ] Set retention as soon as the log group first appears:

      ```bash
      aws logs put-retention-policy \
        --log-group-name "/aws/containerinsights/<cluster-name>/application" \
        --retention-in-days 14 --region <region>
      ```

* [ ] Sample traces: `OTEL_TRACES_SAMPLER=parentbased_traceidratio`,
      `OTEL_TRACES_SAMPLER_ARG=0.1`. `parentbased` keeps browser-sampled traces
      whole across the tier boundary. Under Application Signals the `xray`
      sampler with a centralized rule endpoint is also available.
* [ ] Transaction Search indexes 1% of spans free; raising it raises cost.
* [ ] ⚠️ `main.py:46` logs **every** request at DEBUG on both entry and exit. In
      production that doubles log volume for information the spans already carry.
      Consider demoting once tracing is live.

### 7.3 Verification

* [ ] **Logs:** JSON lines with `trace_id` in
      `/aws/containerinsights/<cluster>/application`. Logs Insights:
      `stats avg(duration_ms) by op`.
* [ ] **Traces:** service map showing `agui-frontend` and `agui-backend` as
      separate nodes with an edge. If they collapse into one, `OTEL_SERVICE_NAME`
      is missing on one of them.
* [ ] **Correlation:** take a slow trace id, convert to X-Ray form (§5), find the
      matching log lines.
* [ ] **Streaming (invariant 1):** open an agent chat, confirm incremental
      tokens. **A regression here is a rollback trigger, not a bug to triage
      later.**
* [ ] **Repo health:** `ruff check` clean, `npm run build && npm run lint` green,
      `./cloud_deploy/scripts/check_agent_sync.sh` OK.

---

## 8. Open questions — answer before starting

1. **Can enterprise browsers reach `client.rum.<region>.amazonaws.com`, and is a
   Cognito identity pool permitted?** If not, §6.3 falls back to a self-managed
   collector on an *internal* load balancer. **The single largest fork here.**
2. **Are X-Ray, Application Signals and Transaction Search enabled/permitted in
   the enterprise account?** It has no Bedrock model access (hence the gateway
   fork) — worth confirming CloudWatch/X-Ray are not similarly restricted before
   building on them.
3. **RDS Postgres available, or does the platform DB stay SQLite?** If SQLite,
   the backend is pinned to one replica with a PVC, and that constraint should be
   written down rather than discovered.
4. **Region, cluster name, namespace, ingress hostnames** for frontend and
   backend. Every `<placeholder>` above needs these; none has been guessed.
5. **One environment or several?** Decides §4's (a) vs (b), which is a code
   change in the (b) case.

Suggested order to chase them: 3 (easiest to learn, constrains the most), then 1
(biggest design fork), then 2. Items 4 and 5 are fill-in-the-blank and do not
reshape the plan.

---

## 9. Impact on architecture invariants

| Invariant | Impact |
|---|---|
| 1 — never buffer the SSE proxy | **At risk.** The §6.1 spike is a hard gate. |
| 2 — DB-backed catalog, no agent id in env | Unaffected, but §4 makes the DB external. |
| 3 — two auth layers | Layer B changes credential *source* (IRSA), not mechanism. |
| 4 / 7 — agent fork, `cloud_deploy/` | **Unaffected.** Agents run on AgentCore, not EKS. No `sync_agents.sh` run needed. |
| 5 — A2UI rich catalog | Unaffected. |
| 6 — modified Next.js 16 | Read the vendored docs before §6.2. Done for this research. |
