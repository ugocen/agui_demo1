# Agents

Five independent AI agents that run on **Amazon Bedrock AgentCore Runtime**. Each
one is packaged and deployed as its own zip; they share no runtime process and no
imports.

This folder contains the agent sources plus the two scripts that build and deploy
them. You do not need this folder to *run* the application day to day — the
backend discovers deployed agents automatically. You need it to **build and
deploy** an agent, or to change an agent's prompt or model.

Everything below is written for **Windows 11 running Ubuntu under WSL2**.

---

## The five agents

| Agent (folder = deploy name) | Framework | What it does |
| --- | --- | --- |
| `sdlc-planner-strands` | Strands | Backlog refinement and sprint planning. Drafts user stories and estimates. **The only agent with server-side tools** (`tools.py`). |
| `release-readiness-langgraph` | LangGraph | Pre-deployment readiness assessment: checks → risk matrix → go/no-go. Pauses for a human decision via LangGraph `interrupt()`. |
| `bug-report-strands` | Strands | Turns a described problem into a structured bug report the user edits in a form. |
| `a2ui-demo-strands` | Strands | Pure generative UI — `tools=[]`, answers by rendering an A2UI surface (charts, diagrams, markdown). |
| `press-release-strands` | Strands | Drafts and revises a press release using editable cards. |

Each agent directory is **self-contained**: its own `agent.py`, its own
`requirements.txt`, and its own copy of `model_factory.py`.

> **The `model_factory.py` copies are byte-identical on purpose.** They must stay
> that way — each zip carries its own copy because each is an independent package.
> If you edit one, mirror the change into the other four.

---

## The LLM provider — read this first

This is the part that matters most in the enterprise environment.

**These agents can only talk to the gateway.** There is no provider switch and no
Amazon Bedrock code path in this build — not a disabled one, not a fallback: the
code simply is not there. No environment variable, and no mistake in the console,
can send a model call to Bedrock.

```
BEDROCK_ENDPOINT_URL + BEDROCK_API_KEY + BEDROCK_MODEL_ID are MANDATORY.
Missing any one -> RuntimeError at startup. There is nothing to fall back to.
```

Model calls go to the **GenAI marketplace API gateway**, authenticated with an
**`x-api-key` header**. Internally the agent builds a `bedrock-runtime` client
pointed at your endpoint with dummy static credentials and a placeholder region,
and registers a hook that injects the key on `Converse`, `ConverseStream` and
`CountTokens`. The SigV4 signature it still computes is ignored by the gateway.

This build is deliberately one-way. An earlier version chose the provider from
the environment and fell back to Bedrock whenever a variable was empty — silently,
in an account that has no Bedrock model access. The provider is now fixed by which
build you are running, so that failure mode cannot occur.

**What a missing variable looks like:** the agent raises before its HTTP server
binds, so the runtime never answers `/ping`, never goes healthy, and the invoke
fails with an initialization timeout — indistinguishable from a wrong-port bug
unless you read the logs. The actual `RuntimeError` naming the missing variable is
in the runtime's `[runtime-logs]` CloudWatch stream.

### Environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| `BEDROCK_ENDPOINT_URL` | **Yes** | **Base URL only** — e.g. `https://genaiapigwna.jnj.com` |
| `BEDROCK_API_KEY` | **Yes** | Sent as the `x-api-key` header. Never commit it. |
| `BEDROCK_MODEL_ID` | **Yes** | E.g. `global.anthropic.claude-sonnet-4-5-20250929-v1:0`. There is **no default** in this build — the agent raises without it. |
| `BEDROCK_STREAMING` | Optional | `true` (default) or `false`. |
| `AWS_REGION` | Not read by the agent | `model_factory.py` pins the client's region to a non-routable placeholder on purpose. Only the deploy tooling uses this (S3 + the AgentCore control plane). |

### The classic mistake: `BEDROCK_ENDPOINT_URL` is a BASE URL

botocore appends the operation path itself. Given the base URL and the model id,
it calls `https://<base>/model/<BEDROCK_MODEL_ID>/converse`.

```
CORRECT:   BEDROCK_ENDPOINT_URL=https://genaiapigwna.jnj.com
WRONG:     BEDROCK_ENDPOINT_URL=https://genaiapigwna.jnj.com/model/<id>/converse
WRONG:     BEDROCK_ENDPOINT_URL=https://genaiapigwna.jnj.com/converse
```

A full path here produces 404s or malformed-URL errors from the gateway.

### `BEDROCK_STREAMING`

Set `BEDROCK_STREAMING=false` **if the gateway does not proxy
`converse-stream`**. This only changes how the agent talks to the model. The user
still sees a streaming response either way — AG-UI rebuilds the token stream
locally before it reaches the browser.

### Personal / dev vs enterprise

| | Personal / dev | **Enterprise** |
| --- | --- | --- |
| Provider | Amazon Bedrock | **GenAI marketplace API gateway** |
| How it is selected | Not selected — a **separate build** (`Phase0/agents/`, Bedrock-only) | Not selected — **this build** is gateway-only |
| Auth on model calls | AWS SigV4 (host credential chain) | **`x-api-key` header** |
| Typical model id | Claude Haiku 4.5 (that build's default) | `global.anthropic.claude-sonnet-4-5-20250929-v1:0` (mandatory here) |
| Needs Bedrock access in the AWS account | Yes | No |

---

## Prerequisites (inside WSL)

Keep this folder on the **Linux filesystem** (e.g. `~/apps/agents`), **not** under
`/mnt/c/...`. Unzip the delivery inside WSL. `/mnt/c` is slow and causes
permission and line-ending problems.

```bash
# Build tooling
sudo apt update && sudo apt install -y zip unzip file

# uv (installs and manages Python for you)
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv python install 3.13

# The scripts arrive from a zip built on macOS — restore the executable bit
chmod +x scripts/build_zip.sh
```

You also need **AWS credentials inside WSL** (`~/.aws/credentials` or exported
environment variables) with access to S3 and `bedrock-agentcore-control`, for the
scripted deploy path.

> **Line endings.** These files must stay LF. `.gitattributes` in this folder
> enforces that. Also run `git config --global core.autocrlf false` in WSL — a
> `build_zip.sh` checked out with CRLF fails with
> `bad interpreter: /usr/bin/env bash^M`.

> **Corporate proxy.** If your network requires a proxy, `uv` and `pip` may need
> index or certificate configuration before dependency installs succeed. Use
> whatever settings your platform team provides.

---

## Configure

```bash
cp .env.example .env
```

Edit `.env` and fill in `BEDROCK_API_KEY`, `DEPLOY_BUCKET` and
`EXECUTION_ROLE_ARN`. The gateway URL and model id are pre-filled. Every variable
is documented inline in `.env.example`.

`.env` is gitignored. Never commit it.

---

## Step 1 — Build the zip (both deploy paths need this)

```bash
./scripts/build_zip.sh ./sdlc-planner-strands
# -> OK: .../build/sdlc-planner-strands.zip (NN MB zipped, NN MB unzipped)
```

Pass the agent **directory**. The zip lands in `build/<agent-name>.zip`.

`build_zip.sh` is strict on purpose — it fails loudly instead of shipping a zip
that AgentCore rejects at runtime. It enforces:

- Dependencies installed as **linux/arm64** wheels only (`aarch64-manylinux2014`,
  `--only-binary=:all:`) — every `.so` is verified to be ARM64.
- **Python 3.13**.
- **`agent.py` at the zip root** (verified by listing the zip).
- **250 MB zipped / 750 MB unzipped** limits.
- File permissions normalized to 644 files / 755 dirs.

Repeat for each agent you want to deploy.

---

## Step 2 — Deploy to AgentCore

Two paths produce an equivalent runtime. Pick one.

### Path A — AgentCore Console (manual)

Use this when you do **not** have S3 or IAM role access from your workstation.

1. Open the **Bedrock AgentCore** console → **Agent Runtimes** → create a runtime.
2. **Upload the zip** from `build/<agent-name>.zip`.
3. Set:
   - **Runtime**: `PYTHON_3_13`
   - **Entry point**: `agent.py`
   - **Server protocol**: **`AGUI`**  ← the backend only discovers AGUI runtimes
   - **Network mode**: `PUBLIC`

   > **The entry point has to end up as `["opentelemetry-instrument", "agent.py"]`**,
   > or the runtime emits stdout logs and no traces at all. The console's *Entry
   > point* field takes a single file, so if it will not accept the prefix, create
   > the runtime here and patch it after step 4:
   >
   > ```bash
   > aws bedrock-agentcore-control update-agent-runtime \
   >   --agent-runtime-id <runtime-id> \
   >   --role-arn <execution-role-arn> \
   >   --network-configuration '{"networkMode":"PUBLIC"}' \
   >   --protocol-configuration '{"serverProtocol":"AGUI"}' \
   >   --environment-variables BEDROCK_ENDPOINT_URL=...,BEDROCK_API_KEY=...,BEDROCK_MODEL_ID=... \
   >   --agent-runtime-artifact '{"codeConfiguration":{"code":{"s3":{"bucket":"<bucket>","prefix":"<key>"}},"runtime":"PYTHON_3_13","entryPoint":["opentelemetry-instrument","agent.py"]}}'
   > ```
   >
   > That call **replaces** the whole configuration, environment variables
   > included — pass them again or step 4's gateway config is wiped and the
   > runtime stops starting.
   >
   > The wrapped entry point only works with a 1.10.0-or-later package: it runs
   > `opentelemetry-instrument` out of the zip, and older zips do not carry it as
   > a runnable file. Mixing them fails as an initialization timeout that says
   > nothing about the cause. Path B sets all of this for you.
4. Set the runtime **environment variables** — this is the only way a deployed agent gets them,
   with no code change:

   | Key | Value |
   | --- | --- |
   | `BEDROCK_ENDPOINT_URL` | `https://genaiapigwna.jnj.com` |
   | `BEDROCK_API_KEY` | *your gateway key* |
   | `BEDROCK_MODEL_ID` | `global.anthropic.claude-sonnet-4-5-20250929-v1:0` |
   | `BEDROCK_STREAMING` | `true` (or `false` if the gateway does not proxy converse-stream) |

5. Save and **wait for status `READY`**.

### Path B — Scripted

```bash
uv run scripts/deploy_agent.py <agent-name> <zip-path>

# example
uv run scripts/deploy_agent.py sdlc-planner-strands ./build/sdlc-planner-strands.zip
```

`uv run` reads the script's inline dependencies and installs boto3 on the fly —
no virtualenv to create.

The script uploads the zip to
`s3://<DEPLOY_BUCKET>/<agent-name>/deployment_package.zip` (creating the bucket if
needed), creates **or updates** the runtime with `serverProtocol: AGUI`, waits for
`READY`, prints the runtime ARN and writes it back into `.env`.

**Required in `.env`:** `AWS_REGION`, `DEPLOY_BUCKET`, `EXECUTION_ROLE_ARN`,
`BEDROCK_MODEL_ID`. Add `BEDROCK_ENDPOINT_URL`, `BEDROCK_API_KEY` and
`BEDROCK_STREAMING` to push the gateway config onto the runtime. If you set
`AUTH_MODE=entra`, then `ENTRA_DISCOVERY_URL` and `ENTRA_ALLOWED_AUDIENCE` also
become required.

> **Redeploys merge environment variables — they do not wipe them.**
> AgentCore's `update_agent_runtime` **replaces** the whole environment-variable
> map. The script therefore reads the runtime's current variables first and
> merges its own on top. A gateway key you set by hand in the console **survives**
> a later scripted redeploy. (Values present in `.env` do overwrite the
> runtime's, so keep `.env` correct.)

Accepted `<agent-name>` values — exactly these seven:

```
sdlc-planner-strands
release-readiness-langgraph
bug-report-strands
a2ui-demo-strands
press-release-strands
jira-story-strands
whoami-strands
```

### Changing runtime config without re-uploading a zip

```bash
uv run scripts/deploy_agent.py <agent-name> --config-only
```

Applies the runtime configuration this script owns — the request-header
allowlist, the inbound authorizer, environment variables — to a runtime that
already exists, keeping the code it is currently serving. No build, no upload,
no 37-51 MB across the wire, and the deployed bytes of a working agent are not
replaced to change a config field.

This is the way to pick up the header allowlist described below on runtimes you
have already deployed. It fails if the runtime does not exist yet — the first
deploy of an agent always needs a zip.

> **Runtimes forward no header to agent code unless they allowlist it.**
> AgentCore drops every request header the runtime did not ask for — including
> `Authorization`, and including the
> `X-Amzn-Bedrock-AgentCore-Runtime-Custom-*` headers the backend proxy uses to
> relay the caller's identity (`AGENT_TOKEN_RELAY=1`). That prefix makes a header
> *eligible* for the allowlist, not exempt from it. A runtime deployed by an
> earlier version of this script has no allowlist and reaches agent code with
> exactly two platform-injected headers (`baggage`, `workloadaccesstoken`), so an
> identity-aware agent sees no caller at all — check yours with
> `aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id <id>`.
> This script now sets the allowlist on every runtime it deploys; existing
> runtimes need one `--config-only` run each.

---

## Step 3 — After deploy

**There is nothing else to configure.** No agent id, ARN or per-agent setting goes
into the backend's environment.

- The **backend** discovers AGUI-protocol runtimes from the AgentCore control
  plane and registers them in its catalog automatically. It only needs
  `AWS_REGION` and AWS credentials.
- **Restart the frontend** so its CopilotKit runtime picks up the new agent list.

The agent then appears in the UI.

### Testing the runtime you just uploaded

An AGUI runtime cannot be tested with the console's plain "Test" panel the way a
normal agent can. It does not take a prompt and return a JSON answer — it speaks
the AG-UI protocol: `POST /invocations` receives a **RunAgentInput** object and
streams back Server-Sent Events. The console shows raw bytes, so it works only if
you hand-craft a valid RunAgentInput and read the SSE yourself.

Three ways to test, cheapest first:

1. **Straight at AgentCore, no backend** — the earliest check, right after upload:

   ```bash
   AWS_REGION=us-east-1 uv run scripts/invoke_agentcore.py a2ui-demo-strands
   # or pass a full runtime ARN, and an optional prompt:
   AWS_REGION=us-east-1 uv run scripts/invoke_agentcore.py <runtime-arn> "Say hi"
   ```

   It builds the RunAgentInput, SigV4-signs an `InvokeAgentRuntime` call, and
   renders the event stream. Exit 0 means the runtime booted and streamed AG-UI
   events. A `RUN_ERROR` naming an *initialization* timeout means the container
   never went healthy — wrong port, or a missing `BEDROCK_*` variable; the real
   traceback is in the runtime's `[runtime-logs]` CloudWatch stream. Needs only
   `AWS_REGION` and AWS credentials.

2. **Through the whole stack** — once the backend is running, `smoke_test.py`'s S0
   probes every registered agent the same way the browser will reach it (catalog →
   proxy → SigV4). See the backend README.

3. **Interactively** — open the frontend and use the agent from the chat UI.

---

## Run an agent locally (optional)

Each `agent.py` is a runnable server. On startup it loads this folder's `.env` via
python-dotenv (real environment variables take precedence), so gateway mode works
locally with the same config you deploy.

```bash
cd sdlc-planner-strands
uv venv .venv -p 3.13
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python agent.py
```

It serves `POST /invocations` (SSE) and `GET /ping` on:

| Agent | Port |
| --- | --- |
| `sdlc-planner-strands` | 8080 |
| `release-readiness-langgraph` | 8080 |
| `bug-report-strands` | 8080 |
| `a2ui-demo-strands` | 8080 |
| `press-release-strands` | 8080 |

All five serve 8080, which is the port AgentCore health-checks. Two of them used
to serve 8090/8091 as local side-by-side dev ports; on AgentCore that meant
nothing ever answered `/ping`, the runtime never went healthy, and every invoke
failed with an initialization timeout. Do not reintroduce a per-agent port.

A locally running agent **cannot be reached through the backend.** The backend
proxy resolves every target from its catalog entry's AgentCore `runtime_arn` and
SigV4-signs the call to AgentCore; it has no local-agent override. So a local run
is for exercising the agent process on its own — post an AG-UI request straight to
its `/invocations` endpoint, or check liveness with `curl localhost:<port>/ping`.
To see an agent in the web UI, deploy it to AgentCore (above).

---

## Layout

```
agents/
├── .env.example                    # config template — copy to .env
├── .gitattributes                  # forces LF (keeps build_zip.sh runnable in WSL)
├── .gitignore
├── README.md
├── scripts/
│   ├── build_zip.sh                # build one agent -> build/<name>.zip
│   └── deploy_agent.py             # upload + create/update the AgentCore runtime
├── sdlc-planner-strands/
│   ├── agent.py                    # entry point (must be at the zip root)
│   ├── tools.py                    # server-side card tools (this agent only)
│   ├── model_factory.py            # gateway-only provider — identical in all 5
│   └── requirements.txt
├── release-readiness-langgraph/
│   ├── agent.py
│   ├── graph.py                    # the 3-node state graph + interrupt()
│   ├── model_factory.py
│   └── requirements.txt
├── bug-report-strands/             # agent.py, model_factory.py, requirements.txt
├── a2ui-demo-strands/              # agent.py, model_factory.py, requirements.txt
└── press-release-strands/          # agent.py, model_factory.py, requirements.txt

build/                              # created by build_zip.sh — gitignored
```

---

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `bad interpreter: /usr/bin/env bash^M` | `build_zip.sh` has CRLF endings. `git config --global core.autocrlf false`, re-check out, and confirm `.gitattributes` is present. |
| `Permission denied` running `build_zip.sh` | `chmod +x scripts/build_zip.sh` — the executable bit is lost in the zip transfer. |
| `FAIL: non-ARM64 native binaries found` | Do not `pip install` by hand; use `build_zip.sh`, which pins the arm64 wheel flags. |
| `FAIL: agent.py is not at the zip root` | You zipped the folder instead of its contents. Use `build_zip.sh`. |
| 404 / malformed URL from the gateway | `BEDROCK_ENDPOINT_URL` has a path on it. It is a **base URL only**. |
| Model calls fail with an AWS credentials or access-denied error | **Not a fallback** — this build cannot call Bedrock. Suspect the gateway rejecting the request, or the runtime being unable to reach `genaiapigwna.jnj.com` from AgentCore's public network. Read `[runtime-logs]`. |
| Streaming errors from the gateway | Set `BEDROCK_STREAMING=false` on the runtime. |
| Agent does not appear in the UI | Runtime is not `READY`, its `serverProtocol` is not `AGUI`, or the frontend was not restarted. |
