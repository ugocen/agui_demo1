---
description: Start the backend and frontend locally for manual testing
---

Bring Phase 0 up locally so I can try it in a browser:

1. Ensure `Phase0/.env` exists (copy from `Phase0/.env.example` if not).
2. Backend (background):
   ```bash
   cd Phase0/backend
   uv venv .venv -p 3.13 && uv pip install --python .venv/bin/python -r requirements.txt
   .venv/bin/uvicorn app.main:app --port 8000
   ```
   Confirm `curl localhost:8000/healthz` is ok.
3. Frontend (background):
   ```bash
   cd Phase0/frontend
   npm install && npm run dev
   ```
   Report http://localhost:3000.

To test the release agent locally without AWS, run it standalone on `:8080`
and start the backend with
`LOCAL_AGENT_URL_RELEASE=http://127.0.0.1:8080/invocations`. Run both servers
in the background so the session stays interactive.
