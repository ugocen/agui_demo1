# Phase 0 — EKS migration and PostgreSQL integration

Status of the work to run Phase 0 on an enterprise Amazon EKS cluster backed by
Amazon RDS PostgreSQL. Covers PR #60 (containerisation and the PostgreSQL
switch) and the hardening pass that followed it.

Phase 0 was built to run locally: SQLite, a hardcoded CORS origin, and no
container images. SQLite alone rules out a multi-pod deployment — it is a file
on one pod's disk, so two replicas are two different databases.

---

## 1. Application changes

### Backend

- **CORS is configurable.** `app/main.py` reads `CORS_ORIGINS`, falling back to
  `http://localhost:3000`. Required on Kubernetes: the browser calls the backend
  directly for `/api/me`, `/api/agents`, `/api/agui/{id}/health` and
  `/api/admin/*`, so the frontend's public origin is cross-origin and every one
  of those calls is blocked until it is listed. A wildcard is not an option —
  the app sends credentials, and browsers reject `*` on a credentialed request.
- **PostgreSQL driver bundled.** `asyncpg==0.30.0` is in `requirements.txt`; it
  previously had to be installed by hand. `DATABASE_URL` switches the app over
  with no code change.
- **The schema belongs to Alembic outside SQLite.** `init_db()` runs
  `create_all` only for the SQLite default. Elsewhere it logs and returns.

  This is the one behavioural change worth understanding rather than just
  noting. `create_all` writes the tables but no `alembic_version` row. A backend
  pod that reached the database before the migration Job therefore left Alembic
  looking at an unstamped database that already had every table, and
  `alembic upgrade head` failed on its first CREATE TABLE with no rerun that
  cleared it. With several replicas, every pod raced into the same create. The
  ordering is now explicit: migration Job to completion, then the Deployment.

### Frontend

- **Standalone build output.** `next.config.ts` sets `output: "standalone"`,
  producing a self-contained `server.js` (~65 MB, against a full `node_modules`
  tree) — a prerequisite for a reasonable image. `next dev` ignores it, so local
  development is unaffected.

---

## 2. Container images

Multi-stage Dockerfiles for both components, with a `.dockerignore` each.

**Backend** (`python:3.13-slim`) — one Uvicorn worker, because pre-fork breaks
OpenTelemetry's Python instrumentation (workers export nothing after the fork);
scaling is by replica. `PYTHONUNBUFFERED=1` keeps the AG-UI SSE stream
unbuffered per architecture invariant 1, and `PYTHONDONTWRITEBYTECODE=1` is what
lets the pod run with a read-only root filesystem. Runs as uid 1001.

**Frontend** (`node:22-alpine`, three stages) — runs as uid 1001, and copies
`public/` and `.next/static/` explicitly, which `.next/standalone` does not
include.

Both images run as non-root because a cluster enforcing the `restricted` Pod
Security Standard rejects a root container at admission — an image that only
works as root cannot be scheduled at all.

### The two backend URLs

The single most confusable piece of configuration, and worth stating plainly:

| Variable | Read by | When | Value |
| --- | --- | --- | --- |
| `NEXT_PUBLIC_BACKEND_URL` | The **browser** (`src/lib/config.ts`) | Baked at image **build** time | The backend's **public ingress hostname** |
| `BACKEND_URL` | The **frontend pod**, server-side (the `/api/copilotkit` route handler, which carries the SSE stream) | **Run** time | The in-cluster Service URL |

An in-cluster Service name in the first one is unresolvable from a user's
browser: the app loads and then every API call fails in the console. The same
public hostname must also appear in the backend's `CORS_ORIGINS` and as the
second host in the ingress — three places, one value.

`NEXT_PUBLIC_*` values are compiled into the client bundle, so they cannot be
supplied by pod environment variables. Changing a tenant id means a new image.
The frontend build now refuses `NEXT_PUBLIC_AUTH_MODE=entra` with an empty
tenant or client id rather than producing an image that builds cleanly and fails
at sign-in.

---

## 3. Kubernetes manifests

`Phase0/deploy/k8s/` — namespace (enforcing `restricted`), IRSA service account,
ConfigMap, Secret template, Alembic migration Job, both Deployments and
Services, an optional HPA, and the ingress.

Most of the non-obvious settings exist because the chat is a Server-Sent Events
stream held open for the length of an answer:

- **The ingress must not buffer.** ingress-nginx buffers upstream responses by
  default, which does to the stream exactly what invariant 1 forbids the backend
  from doing — tokens collect in the proxy and arrive as one block at the end.
  The app looks frozen, then dumps everything. `proxy-buffering: "off"` is what
  makes streaming stream. An ALB does not buffer, but its idle timeout still
  applies.
- **Timeouts.** The 60s ingress default severs longer runs mid-answer; raised to
  an hour.
- **Termination.** 120s grace period, so in-flight answers finish during a
  rollout instead of being cut off. The HPA's scale-down window is long for the
  same reason — removing a pod ends the streams it holds.
- **No CPU limits.** CFS throttling on a streaming hop shows up as stalled
  tokens mid-answer; the CPU *request* is what reserves capacity.

`/healthz` is the probe target: unauthenticated, and it does not touch the
database. A probe that queried Postgres would restart every pod during a
database blip and turn a recoverable outage into a crash loop.

The backend gets AWS credentials through IRSA rather than a static key. The role
needs to invoke the AgentCore runtimes **and** to list them from the control
plane — the catalog is discovered at boot, so without the list permission the
app starts with an empty agent list and nothing the user can see explaining why.

---

## 4. Enterprise delivery

The enterprise side receives zips, not a git remote. The manifests ship as a
fourth payload tree, `deploy/`, alongside `backend/`, `frontend/` and `agents/`;
it describes both components plus the ingress, migration Job and service account
that belong to neither. `win_deployed/deploy/README.md` is the operator's guide.

`scripts/_payload.sh` now owns the list of trees in one place — it had been
hardcoded separately in four scripts, which is four chances to add a tree to the
sync while the drift check quietly does not cover it.

The delivery zips themselves are cut separately: `win_deployed/dist/` is behind
by several changes, and a version bump plus `make_zips.sh` /
`make_agentcore_zips.sh` is its own release step.

---

## 5. What was verified, and what was not

**Verified:**

- `alembic upgrade head` against a live RDS PostgreSQL 16.9 instance over TLS,
  applying all three migrations into a dedicated `agui` schema; the backend then
  booted against it and served `/healthz`. TLS is `?ssl=require` — asyncpg's
  spelling; `?sslmode=require` is libpq's and asyncpg rejects it.
- `init_db()` skips `create_all` on PostgreSQL: pointed at an unroutable
  Postgres host it returns immediately with its log line rather than attempting
  a connection. The SQLite path still creates both tables.
- `ruff` clean across `Phase0/agents`, `Phase0/backend/app` and
  `cloud_deploy/agents`; the agent fork in sync; frontend `npm run build` and
  `npm run lint` green with `output: "standalone"`.
- All eleven manifests parse as YAML; `check_sync.sh` green with the new tree.

**Not verified — no Docker daemon and no cluster access from this machine:**

- Neither image has been built. The Dockerfiles are reviewed, not executed.
- The manifests have not been applied, and have not been validated against the
  Kubernetes API schemas (no `kubectl`/`kubeconform` available) — only parsed as
  YAML. Treat them as reviewed templates: every environment-specific value is
  marked `REPLACE:`.

---

## 6. Remaining work for the enterprise operator

1. Provision RDS PostgreSQL reachable from the cluster subnets; put
   `DATABASE_URL` in a Secret (or source it from Secrets Manager via the CSI
   driver / External Secrets).
2. Create the IAM role and bind it to the `agui-backend` service account via the
   cluster's OIDC provider.
3. Build and push both images to the internal registry, passing the frontend's
   `NEXT_PUBLIC_*` build args.
4. Replace the `REPLACE:` values in the manifests — image references, hostnames,
   role ARN, TLS Secret, region.
5. Run the migration Job to completion, then apply the Deployments.

---

## 7. Test infrastructure to clean up

The PostgreSQL verification in section 5 used a real RDS instance in the
personal AWS account: `agui-test-pg`, `db.t3.micro`, 20 GB, publicly accessible
with its security group restricted to a single home IP. **It is still running.**
It has served its purpose — delete it when convenient.
