---
description: Start the backend and frontend locally for manual testing
---

## Steps

### 1. Env
- Ensure `Phase0/.env` exists (copy from `Phase0/.env.example` if not) with
  `AWS_REGION`, `AUTH_MODE` (`iam` for local dev), and the deployed
  `*_RUNTIME_ARN` values are not required — the catalog is populated live from
  AgentCore on backend startup.

### 2. Backend (background)
```bash
cd Phase0/backend
uv venv .venv -p 3.13 && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000
```
- Confirm `curl localhost:8000/healthz` returns `{"status":"ok"}`.

### 3. Frontend (background)
```bash
cd Phase0/frontend
npm install
npm run dev   # http://localhost:3000
```

### 4. Running an agent standalone (it will NOT reach the backend)
- You can run an agent process on its own for debugging, but the backend cannot be
  pointed at it. `agui_proxy.py` resolves every target from the DB catalog entry's
  AgentCore `runtime_arn` and SigV4-signs the call; there is no local override.
  `LOCAL_AGENT_URL_*` was that mechanism and no longer exists in the code.
  Post an AG-UI request straight to the agent's `/invocations`, or check liveness
  with `curl localhost:8080/ping`.

Run both servers in the background so the session stays interactive.
