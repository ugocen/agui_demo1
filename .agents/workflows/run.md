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

### 4. Local agent without AWS (release agent only)
- Run the release agent standalone on `:8080`, then start the backend with
  `LOCAL_AGENT_URL_RELEASE=http://127.0.0.1:8080/invocations` so the proxy
  targets the local process instead of AgentCore. Unset it for real runs.

Run both servers in the background so the session stays interactive.
