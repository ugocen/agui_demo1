# Backend — AG-UI proxy and agent catalog

A thin backend-for-frontend. It authenticates the browser (**Layer A**: Entra ID
SSO, roles derived server-side from AD groups), SigV4-signs every call to Amazon
Bedrock AgentCore (**Layer B**: always SigV4, independent of Layer A), and pipes
the AG-UI SSE stream straight back to the browser **unbuffered**. It also hosts
the DB-backed agent catalog, synced from the AgentCore control plane.

It holds no agent logic and no per-agent code. FastAPI + uvicorn, Python 3.13,
listens on port 8000.

## There is no agent id or ARN in configuration

Agents are **discovered**, not configured. On startup — and on every catalog sync
— the backend lists runtimes from the Bedrock AgentCore control plane in
`AWS_REGION`, keeps the ones whose protocol is `AGUI`, and upserts them into the
platform DB. The proxy routes on the DB entry's runtime ARN.

Consequence for operators: **you never add an agent here.** Deploy the agent to
AgentCore (see the `agents` repo) and it appears in this service automatically.
All this service needs is `AWS_REGION` plus AWS credentials that can list and
invoke those runtimes.

## Prerequisites — Windows 11 + WSL2 (Ubuntu)

Everything below runs **inside WSL**, not in PowerShell.

1. **WSL2 with Ubuntu.** In PowerShell (once, as Administrator):

   ```powershell
   wsl --install -d Ubuntu
   ```

   Reboot if prompted, then open the **Ubuntu** terminal for all further steps.

2. **Keep the code in the Linux filesystem.** Put this repo under your WSL home
   (for example `~/apps/backend`), **not** under `/mnt/c/...`. The `/mnt/c`
   bridge is slow and breaks file watching. Unzip the delivered archive from
   inside WSL:

   The archive already contains a top-level `backend/` folder, so do **not**
   pass `-d backend` (that would nest it as `backend/backend/`):

   ```bash
   mkdir -p ~/apps && cd ~/apps
   unzip /mnt/c/Users/<you>/Downloads/agui-backend-1.0.0.zip
   cd backend
   ```

3. **Python 3.13 + uv.**

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source ~/.bashrc          # or: export PATH="$HOME/.local/bin:$PATH"
   uv --version
   ```

   `uv` downloads a managed Python 3.13 automatically, so a system Python 3.13 is
   not required.

   *Caveat:* behind a corporate proxy or an internal package mirror, `uv` may need
   index/proxy configuration (for example `UV_INDEX_URL`, `HTTPS_PROXY`) before it
   can reach the package index. Use the values your platform team provides — this
   repo does not ship any.

4. **AWS credentials inside WSL.** The backend signs every AgentCore call with the
   default boto3 credential chain, so credentials must exist **in WSL** at
   `~/.aws/` (Windows credentials at `C:\Users\<you>\.aws` are not picked up).
   Either configure a profile / SSO login there, or export credentials in the
   shell that runs uvicorn.

5. **Shell scripts may need the execute bit** after unzipping (the archives are
   produced on macOS): `chmod +x <script>.sh`.

## Setup and run

From the repo root (`backend/`):

```bash
uv venv .venv -p 3.13
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env          # then edit .env — see Configuration
.venv/bin/uvicorn app.main:app --port 8000
```

Add `--reload` for development (`--reload` restarts on file changes; do not use
it for a long-running deployment).

Verify in a second WSL terminal:

```bash
curl http://localhost:8000/healthz
# {"status":"ok"}
```

WSL2 on Windows 11 forwards `localhost`, so `http://localhost:8000` also works
from the Windows browser and from the frontend at `http://localhost:3000` with no
extra networking. If localhost forwarding misbehaves, start uvicorn with
`--host 0.0.0.0`.

Always run uvicorn **from this directory** — `app.main:app` resolves relative to
it. The SQLite path is anchored to the source file, so the DB always lands at
`backend/phase0.db` regardless.

## Configuration

`backend/.env` is the configuration file for this repo. Real process environment
variables override it. Copy `.env.example` — it documents every variable with
enterprise-oriented comments.

This is the complete list of variables the backend reads:

| Variable | Required | Default | Meaning |
| --- | --- | --- | --- |
| `AWS_REGION` | **Yes** | — | Region for AgentCore discovery and invocation. Empty ⇒ HTTP 500 on `/api/agui/*` and `/api/agentcore/runtimes`. |
| `AUTH_MODE` | No | `iam` | `iam` (or `off`) = SSO off, all routes open. `entra` = SSO on. Enterprise uses `entra`. Unknown values are treated as `iam`. |
| `LOG_LEVEL` | No | `DEBUG` | Standard Python level name. |
| `LOG_FORMAT` | No | `console` | `console` (human-readable) or `json` (one JSON object per line). |
| `ENTRA_TENANT_ID` | **Yes in `entra`** | — | Single-tenant pin; the token's `tid` must match. Empty in `entra` mode ⇒ every request 500s (fail-closed). |
| `ENTRA_SPA_CLIENT_ID` | **Yes in `entra`** ¹ | — | Frontend SPA client id; pins the token's `azp`/`appid` (confused-deputy guard). |
| `ENTRA_ALLOWED_CLIENT_IDS` | No ¹ | — | CSV of client ids allowed as `azp`/`appid`. When set, replaces `ENTRA_SPA_CLIENT_ID` as the allowlist. |
| `ENTRA_GROUP_ROLE_MAP` | No | — | JSON `{groupObjectId: roleName}` on one line. Empty ⇒ identity-only (authenticated, no roles). |
| `ENTRA_ADMIN_GROUP_ID` | No | — | AD group object id whose members get the `admin` role. |
| `ENTRA_ADMIN_GROUP_NAME` | No | — | AD group **display name** whose members get the `admin` role (exact match). |
| `ENTRA_ADMIN_EMAILS` | No | — | CSV of emails granted `admin` directly, without a group (bootstrap). |
| `ENTRA_ADMIN_OIDS` | No | — | CSV of AAD object ids granted `admin` directly (bootstrap). |
| `ENTRA_GROUPS_TTL_SECONDS` | No | `300` | Group-membership cache TTL. Lower = faster de-provisioning, more Graph calls. |
| `REQUIRED_ROLE` | No | — (any authenticated user) | Role required to use the platform (agent list + AG-UI proxy). |
| `DATABASE_URL` | No | SQLite `backend/phase0.db` | SQLAlchemy async URL. Postgres: `postgresql+asyncpg://user:pass@host:5432/db`. |

¹ In `entra` mode at least one of `ENTRA_SPA_CLIENT_ID` / `ENTRA_ALLOWED_CLIENT_IDS`
must be set, or every request returns 500.

Note what is **not** here: no agent ids or ARNs (discovered from AgentCore), and no
model or gateway settings — `BEDROCK_ENDPOINT_URL`, `BEDROCK_API_KEY` and
`BEDROCK_MODEL_ID` belong to the agents and are baked into each runtime at deploy
time. The backend never reads them.

## Authentication

Two independent layers. Layer B never depends on Layer A.

**Layer A — browser to backend**, selected by `AUTH_MODE`:

- **`iam`** — SSO off. No token is validated, no roles are derived, every route is
  open. Intended for local bring-up and the first smoke run: a real Microsoft
  login cannot be scripted, so this lets you prove the proxy, AgentCore and the
  agents work before adding SSO. Do not use it on a shared host.
- **`entra`** — SSO on. The frontend sends a delegated **Microsoft Graph** access
  token as `Authorization: Bearer`. The backend pre-checks the claims locally
  (tenant `tid`, authorized party `azp`/`appid`, Graph audience, `exp`/`nbf` with
  a small clock-skew allowance), then calls Graph `/me` — the authoritative check,
  because a Graph token can only be validated by Graph. It then resolves AD-group
  membership via a single targeted `/me/checkMemberGroups` and maps groups to
  platform roles through `ENTRA_GROUP_ROLE_MAP` / `ENTRA_ADMIN_GROUP_ID` /
  `ENTRA_ADMIN_GROUP_NAME`. Identity and group results are cached briefly.

**Roles are always computed server-side from live AD-group membership and are
never taken from the client.** `GET /api/me` reports the backend's view of the
caller so the SPA can show or hide UI — that response is a mirror, not the
decision. Every protected route is default-deny, and any Graph failure yields no
roles (fail-closed).

**Layer B — backend to AgentCore**: always SigV4-signed with the host's AWS
credentials, in every auth mode. The user's Entra token is never forwarded
upstream; once the caller is validated at the platform boundary, the backend calls
AgentCore as the trusted caller.

## Endpoints

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/healthz` | Open | Liveness. Returns `{"status":"ok"}`. |
| `GET` | `/api/me` | Any caller | The backend's view of the caller: mode, identity, roles. Does not enforce a role. |
| `GET` | `/api/agents` | Platform access | Registered, enabled agents from the DB catalog, with `ui_mode`. |
| `GET` | `/api/agentcore/runtimes` | Platform access | Live AgentCore discovery; also syncs newly-found AG-UI runtimes into the catalog. |
| `POST` | `/api/agui/{agent_id}` | Platform access | The AG-UI proxy: SigV4 to the agent's runtime, SSE streamed back unbuffered. |
| `GET` | `/api/admin/catalog` | `admin` role | Full catalog, including disabled entries. |
| `POST` | `/api/admin/catalog/sync` | `admin` role | Force a reconcile against AgentCore. Audited. |
| `PATCH` | `/api/admin/catalog/{agent_id}` | `admin` role | Edit catalog metadata (e.g. `ui_mode`). AgentCore-sourced fields are read-only. Audited. |
| `GET` | `/api/admin/audit` | `admin` role | Audit trail, newest first. `?limit=` (1–1000, default 200). |

"Platform access" = authenticated, plus `REQUIRED_ROLE` if set. In `iam` mode all
role checks are no-ops. Every admin mutation is written to the `audit_log` table
with the acting Entra identity.

## Database

Holds the agent catalog and the admin audit log — no chat content.

- **Default: SQLite** at `backend/phase0.db`. Created automatically on first
  start; gitignored. Nothing to install.
- **PostgreSQL:** set `DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db`
  and install the driver, which is **not** in `requirements.txt`:

  ```bash
  uv pip install --python .venv/bin/python asyncpg
  ```

**Migrations.** Alembic ships with one migration (initial catalog + audit log),
but the app also creates any missing tables at startup. So:

- Doing nothing is fine — start the app and the schema is created.
- If you want Alembic to own the schema, run it **against a fresh database,
  before the first start**:

  ```bash
  .venv/bin/alembic upgrade head
  ```

- If the app has already started and created the tables, `upgrade head` will fail
  with "table already exists". Mark the existing DB as current instead, then
  future migrations apply cleanly:

  ```bash
  .venv/bin/alembic stamp head
  ```

Alembic resolves `DATABASE_URL` exactly the way the app does — `alembic/env.py`
loads the same `.env` file before reading it (both go through `app/env_boot.py`),
so the two never disagree and a `DATABASE_URL` set in `.env` is honoured by
migrations. Run it from this directory.

## Troubleshooting

**`/api/agui/*` fails with a SigV4 / credentials error, or 500 "no AWS credentials
available for SigV4".** The host has no usable AWS credentials in WSL, or they
expired. Refresh them inside WSL (`aws sso login --profile <profile>`, or
reconfigure the profile) and confirm with `aws sts get-caller-identity`. Remember
`~/.aws` must exist in WSL, not on the Windows side.

**500 "AWS_REGION is not set".** `AWS_REGION` is missing from `backend/.env`, or
uvicorn was started before the file existed. Set it and restart.

**Agent list is empty.** One of:
- no AgentCore runtime in `AWS_REGION` uses the `AGUI` protocol (only `AGUI`
  runtimes are catalogued — MCP, A2A and HTTP are ignored by design);
- the credentials lack permission to list runtimes / read runtime details;
- the wrong region.

Check the startup log — the AgentCore sync is best-effort and never blocks boot,
so a failure appears as a `startup AgentCore sync skipped: ...` warning and the
app still serves `/healthz`. Hit `GET /api/agentcore/runtimes` (or the admin
**Sync**) to retry and see the real error.

**Every request returns 500 "server misconfigured".** `AUTH_MODE=entra` with
`ENTRA_TENANT_ID` empty, or with no allowed client id. This is intentional
fail-closed behaviour. Fill both, or set `AUTH_MODE=iam` while bringing the
service up.

**401 in `entra` mode.** In order of likelihood: token from another tenant (`tid`
pin), token issued to a client id that is not allowlisted (`azp`/`appid` pin), the
token is not a Microsoft Graph token, or it is expired/revoked. `LOG_LEVEL=DEBUG`
logs the exact reason for each rejection.

**403 in `entra` mode.** Identity is fine, roles are not. Check `GET /api/me` for
what the backend actually resolved, then check `ENTRA_GROUP_ROLE_MAP` /
`ENTRA_ADMIN_GROUP_ID` and the user's group membership. Note that group results
are cached for `ENTRA_GROUPS_TTL_SECONDS` (default 300s) — a just-changed
membership may take that long to take effect.

**CORS errors from the browser — known constraint.** Allowed origins are currently
hard-coded to `http://localhost:3000` in `app/main.py`. This is correct for the
intended setup (frontend on port 3000, same machine). If you serve the frontend
from any other origin — a different port, a hostname, or HTTPS — browser calls
will be blocked and `app/main.py` must be changed. Restarting or re-configuring
will not fix it; there is no env var for it.

## Bitbucket

This folder is the repository root — the archive unzips to exactly what should be
committed.

```bash
cd ~/apps/backend
git config core.autocrlf false      # do this in WSL: keep LF, never rewrite to CRLF
git init
git add .
git commit -m "Initial import: AG-UI backend"
git remote add origin <your-bitbucket-remote-url>
git push -u origin main
```

`.gitattributes` pins LF for all text files so shell scripts keep working when the
repo is cloned on a Windows machine and used from WSL. `.gitignore` excludes
`.env`, the virtualenv, `__pycache__/` and the local SQLite DB — verify with
`git status` before the first commit that **no `.env` and no `*.db` is staged**.
Commit `.env.example`, never `.env`.
