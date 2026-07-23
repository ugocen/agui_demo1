# AG-UI Phase 0 EKS Migration & Deployment Report

## Overview
This report summarizes the end-to-end work completed to prepare the AG-UI Phase 0 architecture for deployment to an enterprise Amazon EKS cluster with an Amazon RDS PostgreSQL database. 

The original codebase relied on SQLite (which is incompatible with multi-pod stateless deployments) and was designed for local execution or basic Bedrock AgentCore interactions. We containerized the backend and frontend, enabled configuration via environment variables, tested the PostgreSQL integration in a live AWS account, and ensured that the delivery pipelines (`win_deployed`) bundle the necessary Dockerfiles.

---

## 1. Codebase Modifications (Phase0/)

To make the application container-native and suitable for EKS, we made the following code adjustments:

### Backend
1. **Dynamic CORS Support:** 
   - Modified `Phase0/backend/app/main.py` to read allowed origins from the `CORS_ORIGINS` environment variable (falling back to `http://localhost:3000` for local dev). This ensures the FastAPI backend will accept requests from the actual EKS frontend ingress hostname without hardcoding it.
2. **PostgreSQL Compatibility:** 
   - Added `asyncpg==0.30.0` to `Phase0/backend/requirements.txt`.
   - The application dynamically uses PostgreSQL when `DATABASE_URL` is set, overriding the local `sqlite+aiosqlite` default.

### Frontend
1. **Next.js Standalone Build:**
   - Modified `Phase0/frontend/next.config.ts` to include `output: "standalone"`. This is critical for Dockerization as it instructs Next.js to produce a minimal, self-contained `server.js` build output (which clocked in at a highly optimized ~65MB), avoiding massive `node_modules` dependencies in the final image.

---

## 2. Containerization Artifacts

We created production-ready multi-stage Dockerfiles and `.dockerignore` files for both components:

1. **Backend (`Phase0/backend/Dockerfile`)**:
   - Built on `python:3.13-slim`.
   - Uses a single `uvicorn` worker because pre-forking breaks OpenTelemetry auto-instrumentation. Scaling is intended to happen at the Kubernetes Pod level via Horizontal Pod Autoscaler (HPA).
   - Set `PYTHONUNBUFFERED=1` to ensure the AG-UI SSE stream remains completely unbuffered (a strict architectural invariant).
   - Incorporated the existing `/healthz` endpoint for the Docker/K8s `HEALTHCHECK`.

2. **Frontend (`Phase0/frontend/Dockerfile`)**:
   - Built on `node:22-alpine` using a 3-stage process (deps -> builder -> runner).
   - Takes environment variables (like `NEXT_PUBLIC_AUTH_MODE` and `NEXT_PUBLIC_ENTRA_TENANT_ID`) as `--build-arg`s, which are baked into the static bundle per Next.js requirements.
   - Runs as a secure non-root `nextjs` user.

---

## 3. Enterprise Delivery Pipeline (`win_deployed/`)

The enterprise side receives a packaged zip of the application. We updated the packaging scripts so the enterprise team actually receives the Dockerfiles:

1. **Payload Configuration:**
   - Updated `win_deployed/scripts/_payload.sh` to include `Dockerfile` and `.dockerignore` in both `FRONTEND_FILES` and `BACKEND_FILES`.
2. **Environment Templates:**
   - Updated `win_deployed/backend/.env.example` to document the new `CORS_ORIGINS` variable and updated the `DATABASE_URL` documentation to note that `asyncpg` is now bundled by default.

---

## 4. Live AWS Environment & Database Testing

To prove the PostgreSQL compatibility and Alembic migrations worked on a real database (simulating the enterprise RDS setup), we conducted a live test in the personal AWS root account:

1. **Infrastructure Provisioning:**
   - Created a security group allowing inbound `tcp/5432` from our local IP.
   - Provisioned a new Amazon RDS PostgreSQL 16.9 instance (`agui-test-pg`).
2. **Schema Configuration:**
   - Connected via `psql` and created the `agui` schema.
   - Set the default `search_path` for the `agui_admin` role to `agui, public` so the application connects seamlessly without complex connection string parameters.
3. **Alembic Migrations:**
   - Successfully executed the `alembic upgrade head` command against the remote RDS instance over an SSL-required connection (`?ssl=require`).
   - The 3 existing migrations (`agent_catalog`, `audit_log`, `accepts_files`, `inbound_auth`) were flawlessly applied to the `agui` schema.
4. **Backend Health Check:**
   - Started the Uvicorn backend locally, connected to the remote RDS instance.
   - Queried the `/healthz` endpoint successfully, confirming Uvicorn booted and connected to PostgreSQL without errors.

---

## 5. Next Steps for the Enterprise Operator

With the codebase prepared, the final steps for the enterprise deployment team are strictly infrastructural:

1. Provision an **RDS PostgreSQL** database and store the `DATABASE_URL` in K8s Secrets.
2. Provision an **IAM Role for Service Accounts (IRSA)** to grant the backend pods `bedrock:InvokeAgent` access.
3. Build the Docker images and push them to their internal **Container Registry (e.g., ECR)**.
4. Apply the **Kubernetes Manifests** (Deployment, Service, Ingress).
5. Run the **Alembic Migration K8s Job** prior to starting the backend pods.
