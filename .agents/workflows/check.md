---
description: Check environment prerequisites (Python, Node, npm, Docker, project setup)
---

## Steps

### 1. Tools
- Confirm Python 3.13 (`python3 --version` or `uv python list`), Node (>= 20
  recommended for Next.js 16), npm, `uv`, and `git` are installed.
- Docker is optional for Phase 0 (no images are built locally today; note it
  if missing but do not fail on it).

### 2. Project setup
- `Phase0/.env` exists (copy from `Phase0/.env.example` if not; human fills
  AWS values).
- `Phase0/backend/.venv` exists (created by the backend run steps).
- `Phase0/frontend/node_modules` exists (created by `npm install`).
- Ports 8000 (backend) and 3000 (frontend) are free.

### 3. Report
- Summarize ok/warn/fail per item. For any failure, give the exact fix
  command (e.g. `cp Phase0/.env.example Phase0/.env`, `uv venv .venv -p
  3.13`, `cd Phase0/frontend && npm install`).
