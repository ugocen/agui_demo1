# Agent Platform — Kubernetes Deployment

Manifests for running the agent platform on Amazon EKS: the backend, the
frontend, the ingress, the schema migration Job, and the IAM identity the
backend needs to reach Bedrock AgentCore.

This is a standalone repository. It deploys the **backend** and **frontend**
repositories, which you build into container images first. The agents are not
deployed from here — they run remotely on Bedrock AgentCore and are uploaded
with the tooling in the **agents** repository.

---

## 1. What runs where

Three tiers, and it is worth being precise about which one talks to which,
because the configuration mistakes all come from getting this wrong.

| Tier | Runs as | Reaches |
| --- | --- | --- |
| Frontend | Next.js standalone server, 2 pods | The backend Service, in-cluster, for the chat stream |
| Backend | FastAPI + Uvicorn, 2 pods | RDS PostgreSQL, and Bedrock AgentCore over SigV4 |
| Agents | Not in this cluster | — (AgentCore runtimes, invoked by the backend) |

The **browser** talks to *both* the frontend and the backend directly. That is
the detail that catches people out: the backend is not hidden behind the
frontend, so it needs its own public hostname, and the browser's cross-origin
calls to it must be allowed by `CORS_ORIGINS`.

| Path | Who calls | Endpoints |
| --- | --- | --- |
| Identity, catalog, health, admin | The **browser**, directly | `/api/me`, `/api/agents`, `/api/agui/{id}/health`, `/api/admin/*` |
| Chat / AG-UI streaming | The **frontend pod**, server-side | `/api/agui/{id}` |

---

## 2. The three-places rule

The backend's public URL is configured in three places, and each one fails
differently when it is wrong. Set them together or expect to debug them apart.

| Where | Value | Symptom when wrong |
| --- | --- | --- |
| `NEXT_PUBLIC_BACKEND_URL`, a **build arg** of the frontend image | The backend's public ingress hostname | The app loads, then every call fails in the browser console. An in-cluster Service name here is the classic error — the browser cannot resolve it. |
| `CORS_ORIGINS`, in `k8s/11-backend-config.yaml` | The **frontend's** public hostname | Requests reach the backend and the browser throws them away as CORS failures. |
| The second host in `k8s/30-ingress.yaml` | The backend's public hostname | 404 from the ingress controller. |

`NEXT_PUBLIC_*` values are compiled into the JavaScript the browser downloads.
They cannot be changed by pod environment variables — changing one means
rebuilding the frontend image.

---

## 3. Build the images

From the **backend** repository:

```bash
docker build -t <registry>/agui-backend:<tag> .
docker push  <registry>/agui-backend:<tag>
```

From the **frontend** repository — the SSO settings are baked in here, not at
run time:

```bash
docker build \
  --build-arg NEXT_PUBLIC_AUTH_MODE=entra \
  --build-arg NEXT_PUBLIC_BACKEND_URL=https://agui-api.example.internal \
  --build-arg NEXT_PUBLIC_ENTRA_TENANT_ID=<tenant-id> \
  --build-arg NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID=<spa-client-id> \
  -t <registry>/agui-frontend:<tag> .
docker push <registry>/agui-frontend:<tag>
```

The build refuses to proceed with `NEXT_PUBLIC_AUTH_MODE=entra` and an empty
tenant or client id, rather than producing an image that looks configured and
fails at sign-in.

---

## 4. Prerequisites in AWS

1. **RDS PostgreSQL**, reachable from the cluster's subnets. Create the database
   and a role for the application. Verified against PostgreSQL 16.
2. **An IAM role for the backend**, trusted by the cluster's OIDC provider and
   scoped to the service account `system:serviceaccount:agui:agui-backend`. It
   needs to invoke the AgentCore runtimes and to list them from the AgentCore
   control plane — the agent catalog is discovered at boot, so without the list
   permission the app starts with an empty agent list and no visible error.
   `k8s/10-backend-serviceaccount.yaml` carries the trust-policy shape.
3. **A container registry** the cluster can pull from (ECR or the internal one).
4. **An ingress controller.** The manifests are written for ingress-nginx; see
   the note in `k8s/30-ingress.yaml` for the AWS Load Balancer Controller
   equivalents.

---

## 5. Deploy

Every manifest carries `REPLACE:` comments at the values that are specific to
your environment. Work through them before applying anything.

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/10-backend-serviceaccount.yaml
kubectl apply -f k8s/11-backend-config.yaml
```

Create the database Secret imperatively, so the password never lands in a file:

```bash
kubectl -n agui create secret generic agui-backend-secrets \
  --from-literal=DATABASE_URL='postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME?ssl=require'
```

Two details in that URL are not interchangeable: the driver must be
`postgresql+asyncpg` (plain `postgresql://` selects a synchronous driver that is
not installed), and TLS is spelled `?ssl=require` (`?sslmode=require` is libpq's
spelling and asyncpg rejects it).

**Migrate before starting the backend.** On PostgreSQL the schema belongs to
Alembic; the application deliberately does not create tables. A backend pod that
reaches an unmigrated database serves errors, and one that somehow created the
tables itself would leave the migration unable to run at all.

```bash
kubectl apply -f k8s/13-backend-migrate-job.yaml
kubectl -n agui wait --for=condition=complete job/agui-migrate --timeout=5m
```

Then the workloads:

```bash
kubectl apply -f k8s/14-backend-deployment.yaml
kubectl apply -f k8s/15-backend-service.yaml
kubectl apply -f k8s/20-frontend-deployment.yaml
kubectl apply -f k8s/21-frontend-service.yaml
kubectl apply -f k8s/30-ingress.yaml
```

`k8s/16-backend-hpa.yaml` is optional — read the scale-down note in it first.

Order of standup across the whole platform: **agents** (deploy to AgentCore) →
**backend** (discovers the deployed runtimes automatically) → **frontend**.

---

## 6. Upgrades

```bash
kubectl -n agui delete job agui-migrate          # the name is immutable
kubectl apply -f k8s/13-backend-migrate-job.yaml # with the NEW image tag
kubectl -n agui wait --for=condition=complete job/agui-migrate --timeout=5m
kubectl -n agui set image deploy/agui-backend  backend=<registry>/agui-backend:<tag>
kubectl -n agui set image deploy/agui-frontend frontend=<registry>/agui-frontend:<tag>
```

Run the migration Job on the **same image tag** the Deployment is about to run.
An older Job migrates to an older head and the new pods then fail against it.

---

## 7. Streaming is the constraint

The chat is a Server-Sent Events stream held open for the length of an answer,
and most of the non-obvious settings in these manifests exist because of it.

- **The ingress must not buffer.** ingress-nginx buffers upstream responses by
  default, which collects the whole answer and delivers it in one block at the
  end. The app looks frozen and then dumps everything. `proxy-buffering: "off"`
  in `k8s/30-ingress.yaml` is what makes streaming stream. If you replace that
  ingress, carry the annotation over.
- **Timeouts.** The default 60s read timeout severs longer runs mid-answer; the
  manifests raise it to an hour.
- **Termination.** Pods get a 120s grace period so in-flight answers finish
  during a rollout instead of being cut off.
- **One worker per pod.** The backend image runs a single Uvicorn worker
  deliberately — pre-fork workers break OpenTelemetry's Python instrumentation,
  which exports nothing after the fork. Scale with replicas.

---

## 8. Troubleshooting

| Symptom | Cause |
| --- | --- |
| Answers arrive all at once at the end | Ingress buffering is on. Section 7. |
| Answers cut off mid-sentence, roughly a minute in | Ingress read timeout still at its 60s default. |
| App loads, every API call fails in the console | `NEXT_PUBLIC_BACKEND_URL` was baked wrong. Rebuild the frontend image. |
| API calls reach the backend but the browser rejects them | The frontend origin is missing from `CORS_ORIGINS`. |
| Backend pods crash-loop on a database error | The migration Job has not run, or ran against a different database. |
| Backend starts but the agent list is empty | The IAM role cannot list AgentCore runtimes, or `AWS_REGION` is wrong. |
| `alembic upgrade head` fails on the first CREATE TABLE | The tables exist without an Alembic version stamp. The database was populated by something other than the migration. |
| Pods rejected at admission | The namespace enforces the `restricted` Pod Security Standard. Both images run as uid 1001; a modified image that needs root will not schedule. |

Logs are JSON (`LOG_FORMAT=json`), so CloudWatch Logs Insights can query them
directly:

```bash
kubectl -n agui logs -l app.kubernetes.io/name=agui-backend --tail=100 -f
```
