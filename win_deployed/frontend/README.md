# Agent Platform — Frontend

Chat UI for the agent platform. Next.js 16 (Turbopack) + React 19 + CopilotKit v2.

This is a standalone repository. It needs the **backend** repository running to do
anything useful; the agents themselves run remotely on Amazon Bedrock AgentCore
and are reached through the backend.

---

## 1. What this is

A single, generic chat application over a catalog of agents.

- **Generic rendering.** Agent output is rendered through **A2UI** — the agent
  emits UI descriptions and the frontend paints them with the rich catalog
  (Chart, Mermaid, Markdown, Html), plus human-in-the-loop cards for approvals.
- **No per-agent code.** There is no React component per agent. Agents are
  discovered from the backend catalog (which the backend syncs from AgentCore),
  so a newly deployed agent shows up on its own — nothing to write here.

### How it talks to the backend

Traffic goes two different ways, which matters when you configure it:

| Path | Who calls | Endpoint |
| --- | --- | --- |
| Identity, catalog, admin | The **browser**, directly | `GET /api/me`, `GET /api/agents`, `GET /api/agentcore/runtimes`, `/api/admin/*` |
| Chat / streaming | The **Next.js server**, via its own route `/api/copilotkit` | `POST /api/agui/{agentId}` |

The browser uses `NEXT_PUBLIC_BACKEND_URL`. The server-side chat route uses the
non-prefixed `BACKEND_URL`. See [Configuration](#4-configuration).

---

## 2. Prerequisites (Windows 11 + WSL2)

Everything below runs **inside WSL2 (Ubuntu)**, not in PowerShell.

**Keep the code in the Linux filesystem.** Use a path like `~/apps/frontend`.
Do **not** put it under `/mnt/c/...` — that path is slow and breaks the file
watching Next.js needs for hot reload. If the zip was copied to the Windows side,
unzip it from inside WSL into your home directory:

The archive already contains a top-level `frontend/` folder, so do **not** pass
`-d frontend` (that would nest it as `frontend/frontend/`):

```bash
mkdir -p ~/apps && cd ~/apps
unzip /mnt/c/Users/<you>/Downloads/agui-frontend-1.0.0.zip
cd frontend
```

**Node.js 20 LTS or newer** (Next.js 16 requires a modern Node). Install with
nvm inside WSL:

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
exec $SHELL -l
nvm install --lts
node -v      # expect v20.x or newer
```

> If your network requires a proxy for npm, configure it before installing
> (`npm config set proxy ...` / `npm config set registry ...`). Ask your platform
> team for the correct values — do not guess.

---

## 3. Setup and run

```bash
npm install

cp .env.local.example .env.local
# Edit .env.local — see Configuration below. Do this BEFORE starting the server.

npm run dev
```

Open <http://localhost:3000>. WSL2 forwards localhost, so the browser on Windows
reaches the dev server running in WSL without any extra setup.

Production mode:

```bash
npm run build
npm start
```

Available scripts: `dev`, `build`, `start`, `lint`.

---

## 4. Configuration

**Read this section before anything else — most failures are config failures.**

Configuration for this repository lives in **`.env.local`**, using
**`NEXT_PUBLIC_*`** variable names. Start from `.env.local.example`.

> ### Values are inlined at build time
>
> `NEXT_PUBLIC_*` variables are baked into the JavaScript bundle when the dev
> server or the production build **starts**. Editing `.env.local` while
> `npm run dev` is running has **no effect**. Stop the server and start it again,
> or re-run `npm run build`, after every change.

### Variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `NEXT_PUBLIC_AUTH_MODE` | Yes | `iam` | `entra` = Microsoft Entra ID sign-in. `iam` = sign-in disabled. |
| `NEXT_PUBLIC_BACKEND_URL` | Yes | `http://localhost:8000` | Backend URL as reached **from the browser**. |
| `NEXT_PUBLIC_ENTRA_TENANT_ID` | When `entra` | empty | Entra tenant (directory) id. |
| `NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID` | When `entra` | empty | Entra SPA application (client) id. |
| `NEXT_PUBLIC_ENTRA_SCOPES` | No | `User.Read` | Graph scopes at sign-in, comma-separated. |
| `BACKEND_URL` | Only if backend is not on `localhost:8000` | `http://localhost:8000` | Backend URL as reached **from the Next.js server** (chat route). **Also overrides `NEXT_PUBLIC_BACKEND_URL` for the browser** (`next.config.ts` lists it in `env`, and those keys win over `.env.local`) — so if you set it, set it to a URL the browser can reach too. |

> ### Warning — `NEXT_PUBLIC_AUTH_MODE` must match the backend
>
> This value must be the same as the backend's `AUTH_MODE`. If it is left unset
> it falls back to **`iam`**, which **silently disables sign-in**: the app loads
> with no login screen and sends no token. There is no error message — the app
> just quietly runs unauthenticated. Always set it explicitly.

> ### Warning — client id must match the backend
>
> `NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID` must be **identical** to the backend's
> `ENTRA_SPA_CLIENT_ID`. The backend pins the token's `azp` claim to that id as a
> confused-deputy guard, so a mismatch rejects every request.

### Two backend URLs, on purpose

The browser and the Next.js server are different callers and read different
variables:

- The browser reads `NEXT_PUBLIC_BACKEND_URL` (`/api/me`, `/api/agents`,
  `/api/admin/*`).
- The server-side chat route `/api/copilotkit` reads the non-prefixed
  `BACKEND_URL`, defaulting to `http://localhost:8000`.

In the standard setup (backend on `localhost:8000`) the default is correct and
you only need `NEXT_PUBLIC_BACKEND_URL`. **If you move the backend to another
host or port, set both** — otherwise the catalog loads but chat silently keeps
calling `localhost:8000`.

### Prefixed vs non-prefixed names

`next.config.ts` accepts both spellings for each setting and the **non-prefixed
name wins if both are set**:

```
AUTH_MODE  ->  NEXT_PUBLIC_AUTH_MODE  ->  "iam"
```

The non-prefixed names exist for the original monorepo layout, where a shared
`.env` one directory up supplied them. **This standalone repository has no parent
`.env`**, so use the `NEXT_PUBLIC_*` names in `.env.local` and ignore the
non-prefixed ones (except `BACKEND_URL`, noted above). Setting both spellings to
different values is the one way to confuse yourself here — don't.

---

## 5. Authentication (`entra` mode)

1. MSAL signs the user in with a **redirect** flow against your tenant.
2. It acquires a **Microsoft Graph access token** (not an ID token).
3. That token is sent as the `Bearer` token to the backend.
4. The backend calls Graph `/me` with it — that is the authoritative identity —
   and derives platform roles from the user's **AD-group membership,
   server-side**.
5. The client calls `GET /api/me` and mirrors the returned roles to show or hide
   UI (for example the admin screen).

**The client-side role check is cosmetic.** The backend enforces authorization on
every request. Hiding a button is not a security control, and the UI degrades to
"no roles" on failure rather than granting access.

Requirements on the Entra app registration: a **SPA** platform with redirect URI
`http://localhost:3000`, and the `User.Read` delegated Graph permission.

In `iam` mode there is no sign-in, no token, and no roles — local development
only.

---

## 6. Routes

| Route | Purpose |
| --- | --- |
| `/` | Home — agent catalog and discovered AgentCore runtimes, with a rescan action. |
| `/agents/[agentId]` | Chat with one agent. A2UI surfaces and human-in-the-loop cards render here. |
| `/admin` | Catalog admin. Requires the `admin` role in `entra` mode; open in `iam` mode. |
| `/a2ui-preview` | Renders sample A2UI surfaces offline. No backend, no agent, no AWS — useful to prove the render path works. |
| `/api/copilotkit/...` | Internal server route that proxies chat to the backend. Not a page. |

`/a2ui-preview` is the fastest way to confirm the frontend itself is healthy when
you suspect the backend.

---

## 7. Troubleshooting

**The agent list is empty.**
Check in this order: the backend is running and reachable at
`NEXT_PUBLIC_BACKEND_URL`; you are authorized (open `/api/me` on the backend);
the backend's catalog actually has agents (`/admin`, or sync it from AgentCore).
The backend needs AWS credentials to see AgentCore runtimes at all.

**A newly deployed agent does not appear in chat.**
The chat route resolves the agent list on its **first request and caches it for
the process lifetime**. After deploying a new agent, **restart the frontend**
(`Ctrl+C`, then `npm run dev`). Reloading the browser is not enough.

**Config changes do nothing.**
You did not restart. `NEXT_PUBLIC_*` values are inlined at start-up — see
[Configuration](#4-configuration).

**No sign-in screen appears, or nothing is protected.**
`NEXT_PUBLIC_AUTH_MODE` is unset or not `entra` (it defaults to `iam`), or you
changed it without restarting.

**Sign-in redirect loops, or the backend rejects the token.**
Tenant id or SPA client id does not match the backend's, or the app registration
is missing the `http://localhost:3000` SPA redirect URI. Confirm
`NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID` equals the backend's `ENTRA_SPA_CLIENT_ID`.

**CORS errors in the browser console.**
The backend only allows the origin `http://localhost:3000`. Reach the app at
exactly that origin — not `127.0.0.1:3000`, not the WSL IP address.

**Hot reload does not react to file changes.**
The code is on `/mnt/c/...`. Move it into the WSL filesystem (`~/apps/...`).

**A shell script fails with `bad interpreter` or `^M`.**
CRLF line endings. See [Bitbucket](#8-bitbucket-repository).

---

## 8. Bitbucket repository

This folder is the repository root — the frontend is its own repo, separate from
the backend and the agents.

```bash
git config core.autocrlf false     # run this in WSL before committing

git init
git add .
git commit -m "Initial import: agent platform frontend"
git remote add origin <your-bitbucket-remote-url>
git push -u origin main
```

`.gitattributes` pins everything to **LF** so that scripts still run under WSL
after a checkout on a Windows machine. `core.autocrlf false` keeps Git from
rewriting endings behind its back. Leave both in place.

`.gitignore` excludes `node_modules/`, `.next/`, and every `.env*` file —
`.env.local.example` is deliberately tracked as the template. **Never commit
`.env.local`.**

The zips were produced on macOS; if any shell script lost its executable bit
during transfer, restore it with `chmod +x <script>`.
