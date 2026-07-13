# Implementation Plan, Phased with Validation Gates

Each phase ends with a validation gate. We do not start the next phase until the gate criteria pass. Durations are indicative for a small team (2-4 engineers) and can run partially in parallel once Phase 0 passes.

## Phase 0, Validation Spike (2-3 weeks)

Goal: prove the unvalidated core, AG-UI on AgentCore rendered by CopilotKit, with Entra ID tokens end to end. Deliberately minimal: manual deployments and local runs are fine here, productionization begins in Phase 1, afterwards everything moves to its proper place.

Tasks:

* Entra ID setup: one app registration for the frontend (SPA, PKCE) and one for the backend API (exposed scope), a test app role (e.g., `platform.user`) assigned to a pilot AD group
* Build one AG-UI agent with Strands (`ag-ui-strands`), a couple of demo tools, one tool that emits state for generative UI. Start from official sources: the AWS FAST template's `agui-strands-agent` pattern (`awslabs/fullstack-solution-template-for-agentcore`) and the `03-integrations` folder of `awslabs/amazon-bedrock-agentcore-samples`, which includes an official Entra ID inbound-auth integration example. Note that FAST ships with Cognito, CDK, and Amplify, we mine its patterns rather than deploying it as-is since our stack is EKS, Entra ID, and ECR
* Deploy manually for the spike using **direct code deployment** (zip package in S3) through the AWS console, no Docker and no ECR needed at this stage (detailed procedure below). The Jenkins/ECR container pipeline (the production standard, doc 01 decision 11) is intentionally deferred to Phase 1, moving from zip to container later changes only the packaging, the agent code and the runtime contract stay the same
* Minimal FastAPI backend: JWT validation, one proxy route streaming AG-UI SSE from AgentCore to the frontend with the user's bearer token attached
* Minimal Next.js + CopilotKit app: Entra sign-in, chat with the agent, at least one generative UI component and one shared-state interaction, one human-in-the-loop approval
* Run the backend and frontend locally, no EKS and no Temporal in this phase. Database: if the spike needs persistence at all, either point at a small dev RDS instance or run local SQLite behind the same ORM (SQLAlchemy) so the later swap to RDS PostgreSQL is a configuration change, choose whichever is less friction

### Phase 0 deployment procedure, console + S3 (direct code deployment)

Direct code deployment hosts an agent on AgentCore Runtime from a .zip archive of code and dependencies, no Dockerfile, no ECR. Official guides are listed in doc 06 (direct code deployment overview, Python guide, and troubleshooting page). Steps:

1. **Write the agent to the runtime contract.** The entrypoint `.py` file must either use the `@app.entrypoint` pattern from the AgentCore Python SDK or itself serve `/invocations` (POST) and `/ping` (GET). Our AG-UI agent satisfies this through the SDK's AG-UI server helpers (`AGUIApp` / `serve_ag_ui` with the Strands `ag-ui-strands` integration).
2. **Build the package with ARM64 dependencies.** Supported runtimes are Python 3.10 to 3.13. Install dependencies into the package folder as linux/arm64 wheels, e.g. `uv pip install --python-platform aarch64-manylinux2014 --only-binary=:all: -r requirements.txt --target package/`. This matters: AgentCore validates every native binary (`.so`) in the zip for ARM64 and rejects packages containing x86_64 or macOS builds with an "incompatible with Linux ARM64" error.
3. **Zip correctly.** Zip from inside the package folder so the entrypoint sits at the zip root (the entrypoint path configured later must match the path inside the zip exactly). Respect POSIX permissions (644 for files, 755 for directories/executables) and the size limits, 250 MB zipped, 750 MB unzipped. Platform note: on macOS (Stage A) the standard `zip` tool is fine. On Windows 11 (Stage B) build the zip inside WSL, the official guide recommends WSL precisely because AgentCore relies on POSIX permissions that native Windows zipping does not preserve, and if WSL is not permitted on the corporate machine, let the AgentCore CLI handle packaging instead. The ARM64 wheel download in step 2 works identically from macOS and Windows since wheels are fetched for the target platform, not compiled locally.
4. **Upload to S3.** Either upload the zip to a bucket first and note the S3 URI, or use the console's built-in options. The console "Host Agent" flow offers three source choices: start with a template (console creates the bucket and sample code), upload the zip through the console, or point at an existing S3 URI.
5. **Create the runtime in the console.** AgentCore console → Agent Runtime → Host Agent → Source type S3 → select the zip, choose the Python runtime version and the entrypoint file, pick the execution role (auto-create is fine for the spike, the role needs AgentCore runtime permissions, `s3:GetObject` on the package, and CloudWatch Logs permissions), network mode Public for the spike, and set the protocol to AGUI. If the console version in our region does not expose the AGUI protocol option in this form, create the runtime with the same zip via a short boto3 `create_agent_runtime` call using `codeConfiguration` as the artifact and AGUI in `protocolConfiguration`, the S3 package is identical either way.
6. **Configure inbound auth.** Replace the default IAM authorization with a JWT authorizer: Entra ID OIDC discovery URL plus the allowed client IDs/audience, so the token obtained by the local frontend flows through the local backend to the runtime.
7. **Create an endpoint and smoke test.** Choose Create Endpoint (name and version pre-filled), then Test Endpoint opens the console Playground/Sandbox, verify the agent responds there before wiring the local backend and CopilotKit frontend.
8. **Iterate.** Upload a new zip (a new object version works) and update the runtime from the console or with `update_agent_runtime`. Subsequent zip updates deploy noticeably faster than container updates, which is exactly why this path fits the spike.

Known gotcha: the identity calling create/update must itself have `s3:GetObject` on the zip (and `kms:Decrypt` if the bucket uses a customer-managed key), missing caller permissions are the most common console deployment failure. Also note direct code deployment stores artifacts in the service account with S3-rate storage costs.

### Phase 0 execution environments, two stages

**Stage A, personal AWS account, macOS.** Runs first. Root access exists on this account but is used only to bootstrap: enable MFA on root, create a dedicated IAM deployment user, then all work happens as that user, never as root. Least-privilege permission set for the deployment user: AgentCore control-plane actions (create/update/get runtime and endpoint, invoke for testing), S3 on the deployment bucket (create bucket, put/get object), `iam:CreateRole` and `iam:PassRole` for the auto-created execution role (or pre-create the execution role once and keep only PassRole), CloudWatch Logs read for debugging, and Bedrock model invoke. Enable model access for the agent's model in the chosen region, and use the same region later in the corporate account. Backend and frontend run locally on the macOS machine, the agent zip is built and uploaded from there. Costs stay minimal (AgentCore consumption, S3, model tokens).

**Stage B, corporate AWS account, Windows 11 (Cloud PC).** Repeats the exact same direct-code deployment after Stage A passes, using only the assigned corporate role, no root. Verify the role ahead of time against the Stage A permission list, the most likely gap in corporate roles is `iam:CreateRole` (needed by the execution-role auto-create path), so request a pre-created execution role from the account team and rely on `iam:PassRole` only. The caller `s3:GetObject` gotcha from the procedure below applies to the assigned role too. Backend and frontend run locally on the Windows machine, Windows-specific packaging notes are in step 3. Purpose of this stage: prove the flow under real corporate constraints (permissions, network, proxy) before Phase 1 infra work starts in that account.

Entra ID note: the JWT authorizer only needs the public OIDC discovery URL, so the corporate Entra app registrations work fine against the personal AWS account in Stage A. If the app registrations are not ready during Stage A, run Stage A temporarily with default IAM auth and make Entra auth mandatory from Stage B onward.

Validation gate G0:

* A user in the pilot AD group signs in, chats with the agent, sees streaming tokens, a generative UI component renders from agent state, HITL round-trip works
* A user without the app role is rejected with 403
* AG-UI events observed correctly for error and reconnect cases (kill the agent mid-stream and verify frontend behavior)
* Stage B passed: the same deployment reproduced in the corporate account using only the assigned role from the Windows 11 machine, any permission or network gaps documented and requested before Phase 1
* Decision recorded: proceed with AG-UI/CopilotKit, or fall back to plain SSE chat everywhere

## Phase 1, Platform Foundation (3-4 weeks)

Goal: real infrastructure the rest of the project builds on.

Tasks:

* Terraform: VPC, EKS cluster(s), node groups, IRSA/Pod Identity, ECR, RDS PostgreSQL (Multi-AZ), ElastiCache, S3 buckets, Secrets Manager
* Environments: dev and prod at minimum (separate AWS accounts recommended), test/stage if capacity allows
* EKS baseline: ALB Ingress Controller, ExternalDNS, cert-manager, External Secrets Operator, cluster autoscaler or Karpenter
* Observability baseline: install the Amazon CloudWatch Observability EKS add-on (`amazon-cloudwatch-observability`), which provides Container Insights with enhanced observability plus Fluent Bit log shipping in one add-on, enable CloudWatch Transaction Search once per account (prerequisite for AgentCore GenAI Observability), first dashboards and alarms (pod restarts, 5xx, latency)
* CI/CD: Jenkins multibranch pipelines triggered from Bitbucket, Artifactory as pip/npm proxy and internal package host, image builds pushed to ECR with Inspector scanning as a gate, Helm-based deploys per environment, dedicated agent pipeline building linux/arm64 images and updating AgentCore runtimes via the control-plane API, tag-based promotion of identical digests to prod (details in doc 03 section 6). Provision ARM64 build capability for Jenkins (Graviton build agents recommended)
* Process setup: Jira epics per phase with gate-checklist milestone tickets, Confluence space seeded from these documents
* Harden auth: backend JWT middleware productionized, role-to-permission mapping table, admin bootstrap

Validation gate G1:

* `hello-world` frontend and backend deployed to dev through the pipeline, reachable via ALB with TLS, logs and metrics visible in CloudWatch, secrets sourced from Secrets Manager, sign-in works against Entra ID

## Phase 2, Agent and MCP Platform (4-5 weeks)

Goal: the registry-driven core product.

Tasks:

* Agent registry: data model, API, admin UI (register agent, protocol, runtime ARN, required roles, UI capability)
* Promote the Phase 0 agent into the registry as the first entry, add one LangGraph AG-UI agent to prove the single-frontend-parser claim
* AgentCore Gateway: create gateway, configure inbound auth with Entra ID, register first targets
* First custom MCP server on EKS (containerized, streamable HTTP), registered as a Gateway target, plus one API/Lambda target
* MCP registry: data model, API, admin UI, health checks against Gateway targets
* Skills registry v1: bundle format, S3 storage, activation flags, loader library used by the pilot agents (details in doc 04)
* Frontend: agent catalog page, dynamic mounting (CopilotKit surface for `agui` agents, generic chat for `chat` agents)

Validation gate G2:

* A new agent can be added end to end (deploy to AgentCore, register, appears in catalog, correct UI mode, RBAC respected) without frontend code changes for the chat case
* An agent calls a tool on the EKS-hosted MCP server through Gateway with identity-scoped access
* Enabling/disabling a skill changes agent behavior without redeploying the agent

## Phase 3, Data and Durability (3-4 weeks)

Goal: reliability layer and persistent conversations.

Tasks:

* Temporal: Helm deploy on EKS, PostgreSQL persistence database, Web UI behind SSO, workers deployed from the dedicated `temporal-workers` repository through its own Jenkins pipeline
* First workflows: long-running multi-step agent pipeline with retries, an HITL approval workflow (signal-based), a scheduled agent job
* Thread/session persistence: PostgreSQL schema for threads and messages, history view in the frontend, reconnect to an in-flight run
* Redis integration: rate limiting, cache, SSE fan-out across backend replicas if needed
* Backup/restore: RDS snapshots and restore runbook, S3 lifecycle policies

Validation gate G3:

* Kill a worker pod mid-workflow, the workflow resumes and completes
* An HITL workflow waits over an hour and completes after approval
* Chat history survives pod restarts and re-login, a user can reopen an old thread

## Phase 4, Multi-Agent Experience (3-4 weeks)

Goal: the full envisioned UX and agent interoperability.

Tasks:

* A2A: deploy first standard agent with `--protocol A2A`, backend A2A client streaming into the generic chat screen, HTTP/SSE fallback path for simple agents
* Agent-to-agent calls over A2A where a workflow spans agents (orchestrated by Temporal where durability matters)
* Per-agent UI capability metadata driving richer rendering differences (custom components per agent where justified)
* Concurrency and quota controls per user/role, graceful degradation when AgentCore throttles

Validation gate G4:

* AG-UI agent and A2A agent live side by side in the catalog, each renders in its own mode, one composite flow where an agent (or Temporal workflow) delegates to another agent completes successfully

## Phase 5, Production Hardening (3-4 weeks, partially continuous)

Tasks:

* CloudWatch: complete dashboards (platform, per-agent, per-MCP, Temporal), alarm runbooks, log retention and cost tuning, AgentCore GenAI Observability review (token usage, latency, error traces)
* Security: penetration review of the AG-UI proxy and Gateway auth, dependency scanning in CI, network policies between namespaces, least-privilege IAM audit
* Load testing: concurrent SSE sessions, AgentCore concurrency behavior, Temporal throughput
* DR: multi-AZ posture review, restore drills, incident runbooks
* Cost review: AgentCore consumption, CloudWatch ingestion, RDS/ElastiCache sizing
* Documentation and onboarding guide for internal agent developers ("how to ship an agent/MCP/skill to the platform")

Validation gate G5 (go-live):

* Load test targets met, alarms fire and page correctly in a game day, restore drill passed, security findings closed or accepted, onboarding doc validated by a developer outside the core team

## Sequencing Notes

* Executable versions of every phase exist for Claude Code: doc 07 (Phase 0, most detailed), docs 08 to 12 (Phases 1 to 5). Hand Claude Code one phase document at a time, only after the previous gate is signed off

* Phase 0 is strictly first, it de-risks the only genuinely novel integration (AG-UI + AgentCore + CopilotKit + Entra ID)
* Phase 1 infra work can start in parallel during Phase 0 as long as no G0-dependent decisions are baked in
* Skills (Phase 2) and Temporal (Phase 3) can swap order if workflow needs arrive earlier
* Keep a running decision log (doc 05 format) from day one
