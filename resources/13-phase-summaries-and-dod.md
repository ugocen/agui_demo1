# Phase Summaries and Definition of Done

Quick reference across all phases. Each phase has a one-line goal, a short summary, and its Definition of Done (the validation gate that must pass before the next phase starts). Full detail lives in the executable plans (docs 07 to 12).

## Phase 0, Validation Spike (doc 07)

Goal: prove AG-UI on AgentCore rendered by CopilotKit, with Entra ID tokens, end to end.

Summary: two SDLC-themed AG-UI agents (SDLC Planner on Strands, Release Readiness on LangGraph) deployed to AgentCore via direct code deployment (zip in S3), a local FastAPI backend proxying AG-UI, and a local Next.js + CopilotKit frontend rendering generative UI (this plan specified six custom cards; the implementation later pivoted to a fully-generic A2UI catalog — see Phase0/README.md "Generative UI — current state"). Run twice: Stage A on the personal AWS account (macOS), Stage B on the corporate account (Windows 11). No EKS, no Temporal, no pipeline.

Definition of Done (gate G0):
* A pilot-group user signs in, chats, sees streaming tokens, a generative UI card renders from agent state, and a human-in-the-loop round trip completes
* A user without the app role is rejected (403), a request without a token is rejected (401)
* AG-UI error and reconnect handled cleanly (stream killed mid-response, frontend recovers)
* Stage B reproduced in the corporate account with the assigned role only, permission/network gaps documented
* Decision recorded: proceed with AG-UI/CopilotKit, or fall back to plain SSE chat

## Phase 1, Platform Foundation (doc 08)

Goal: real infrastructure and the deployment pipeline in the corporate dev account.

Summary: Terraform for VPC, EKS, RDS PostgreSQL, ElastiCache Valkey, S3, ECR, and IAM, cluster baseline (ALB controller, ExternalDNS, cert-manager, External Secrets, Karpenter), CloudWatch observability add-on plus Transaction Search, shared Helm charts, the Jenkins shared library, and contracts/lib packages published to Artifactory.

Definition of Done (gate G1):
* A hello-world app builds through Bitbucket → Jenkins → ECR (Inspector gate) → Helm and deploys to dev
* Reachable over HTTPS via ALB with valid TLS
* Logs and metrics visible in CloudWatch, secrets delivered from Secrets Manager via ESO
* Entra sign-in works, production-grade app registrations ready

## Phase 2, Agent and MCP Platform (doc 09)

Goal: the registry-driven core product, agents, MCP servers, and skills managed as data.

Summary: FastAPI backend with the agent/MCP/skill registries and RBAC, frontend catalog with dynamic per-agent mounting, agent and MCP template repos, the two Phase 0 agents promoted to container deployments, AgentCore Gateway with Entra inbound auth, the first EKS-hosted MCP server behind the Gateway, and the shared skills lifecycle (S3 bundles, loader, activation).

Definition of Done (gate G2):
* A new agent is onboarded end to end (deploy, register, appears in catalog, correct UI mode, RBAC enforced) with no frontend code change for the chat case
* An agent calls a tool on the EKS-hosted MCP server through the Gateway with identity-scoped access
* Enabling or disabling a skill changes agent behavior on a fresh session without redeploying the agent

## Phase 3, Data and Durability (doc 10)

Goal: Temporal-backed reliability and persistent conversations.

Summary: self-hosted Temporal on EKS (persistence on RDS, Web UI behind SSO), a dedicated worker repository, three canonical workflows (retry pipeline, HITL signal wait, scheduled job), thread and message persistence with history and resume, Redis-backed rate limiting and multi-replica SSE, and a backup/restore drill.

Definition of Done (gate G3):
* Kill a worker pod mid-workflow, the workflow resumes and completes
* An HITL workflow waits over an hour and completes after approval
* Chat history survives pod restarts and re-login, an old thread reopens with full history

## Phase 4, Multi-Agent Experience (doc 11)

Goal: A2A agents alongside AG-UI agents, plus agent-to-agent flows.

Summary: a third SDLC agent (Standup Reporter) served over A2A with the generic chat screen, the backend A2A client, a composite Temporal workflow spanning three agents (sprint review pack), registry-driven card rendering, and per-role quotas with graceful degradation under throttling.

Definition of Done (gate G4):
* An AG-UI agent and an A2A agent are live side by side in the catalog, each rendering in its own mode
* One composite flow where an agent (or Temporal workflow) delegates to another agent completes successfully and durably

## Phase 5, Production Hardening (doc 12)

Goal: production readiness, security, load, DR, cost, and onboarding.

Summary: the prod environment provisioned by promoting identical artifacts, dashboards and alarms as code (including AgentCore GenAI Observability), security hardening with blocking scanners and auth abuse-case tests, load and resilience testing, a DR game day and restore drill, recurring cost reporting, and an externally validated developer onboarding guide.

Definition of Done (gate G5, go-live):
* Load targets met with headroom, no stream corruption at peak
* Alarms fire and page correctly, runbooks proven sufficient in a game day
* Restore drill passed within RTO
* Security findings closed or risk-accepted with ADRs
* Onboarding guide validated by a developer outside the core team
* G5 signed off in Jira, platform declared production
