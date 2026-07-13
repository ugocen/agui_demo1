# AI Agent Platform, Architecture Overview

**Status:** Draft for review
**Date:** 2026-07-11

## 1. Context and Goals

We are building an internal multi-agent platform where different AI agents can be registered, discovered, and used through a single web application. Some agents provide rich generative UI experiences, others provide plain chat. The platform must also let us register MCP servers as shared tool providers and manage reusable skills across agents.

Primary goals:

* Run agents on Amazon Bedrock AgentCore Runtime, framework-agnostic (Strands Agents, LangGraph, or other popular frameworks)
* Serve users through a React/Next.js frontend with CopilotKit (self-hosted, open-source)
* Support two rendering modes: AG-UI capable agents render generative UI via CopilotKit, standard agents render in a generic chat screen and communicate over A2A (preferred) or plain HTTP/SSE
* Host backend (FastAPI) and frontend on Amazon EKS
* Use Temporal (self-hosted, open-source) for durability and reliability of long-running workflows
* Centralize logs and metrics in Amazon CloudWatch for both EKS and AgentCore
* Authenticate with the existing Microsoft Entra ID tenant (SSO), authorize with AD groups mapped to platform roles
* Prefer AWS managed services where an AWS service exists, prefer self-hosted open-source for everything else

## 2. High-Level Architecture

```
                        ┌────────────────────────────────────────────┐
 Browser ──Entra ID──►  │                    EKS                     │
   │  (OIDC, PKCE)      │  ┌──────────────┐    ┌──────────────────┐  │
   │                    │  │ Next.js +    │───►│ FastAPI Backend  │  │
   └──── HTTPS/ALB ────►│  │ CopilotKit   │    │ (BFF, registry,  │  │
                        │  │ Runtime      │    │ RBAC, sessions)  │  │
                        │  └──────────────┘    └───────┬──────────┘  │
                        │  ┌──────────────┐    ┌───────▼──────────┐  │
                        │  │ MCP servers  │    │ Temporal server  │  │
                        │  │ (containers) │    │ + workers        │  │
                        │  └──────▲───────┘    └───────┬──────────┘  │
                        └─────────┼────────────────────┼─────────────┘
                                  │                    │
                        ┌─────────┴────────────────────▼─────────────┐
                        │        Amazon Bedrock AgentCore            │
                        │  Runtime (AGUI / A2A / HTTP protocols)     │
                        │  Gateway (unified MCP endpoint)            │
                        │  Identity (inbound JWT, outbound OAuth)    │
                        │  Memory, Observability (OTEL)              │
                        └────────────────────────────────────────────┘

 Data: RDS PostgreSQL (Multi-AZ), ElastiCache (Redis/Valkey), S3
 Observability: CloudWatch (Container Insights, ADOT, GenAI Observability)
```

## 3. Component Responsibilities

### 3.1 Frontend, Next.js + CopilotKit (EKS)

* Next.js (App Router) with the self-hosted CopilotKit runtime as a Next.js API route (or a small dedicated Node service if we need independent scaling)
* Entra ID sign-in with Authorization Code + PKCE (MSAL or Auth.js with the Entra provider)
* Agent catalog page driven by the registry API, each agent entry declares its capability (`agui` or `chat`)
* AG-UI agents mount CopilotKit components (generative UI, shared state, human-in-the-loop), the CopilotKit runtime connects to the agent through the AG-UI endpoint proxied by the backend
* Standard agents mount a generic chat screen that talks to the backend's chat API, the backend translates to A2A or HTTP/SSE toward the agent

### 3.2 Backend, FastAPI (EKS)

* Backend-for-frontend: validates Entra ID JWTs (JWKS), extracts group/role claims, enforces RBAC on every route
* Agent registry API: CRUD for agents (name, description, protocol, AgentCore runtime ARN, required roles, UI capability flags)
* MCP registry API: CRUD for MCP servers and their Gateway target status (see doc 04)
* Skills registry API: CRUD and activation flags for shared skills (see doc 04)
* AG-UI proxy: forwards AG-UI traffic to AgentCore Runtime `/invocations` (SSE) or `/ws`, attaching the caller's bearer token so AgentCore Identity can authorize inbound requests and scope tools per user
* A2A client: for standard agents, wraps the A2A SDK, streams responses back to the chat screen
* Session and thread persistence in PostgreSQL (the open-source CopilotKit runtime does not persist threads out of the box, we own this)
* Kicks off Temporal workflows for long-running or multi-step agent tasks

### 3.3 Agents, Bedrock AgentCore Runtime

* Every agent is deployed as a **container image in ECR**. AgentCore Runtime requires linux/arm64 images, port 8080, and the `/invocations` (POST) plus `/ping` (GET) contract. Deployment happens from Jenkins via the `bedrock-agentcore-control` API (`create_agent_runtime` / `update_agent_runtime` with the ECR `containerUri`), not via the interactive CLI, so agent deploys follow the same Bitbucket → Jenkins → ECR path as EKS workloads. The `agentcore` CLI remains a local development convenience only
* AG-UI agents: configured with `--protocol AGUI`, expose `/invocations` (SSE) and `/ws` on port 8080. Strands has a first-party integration (`ag-ui-strands`), LangGraph uses `ag-ui-langgraph`. The AWS FAST template ships reference patterns (`agui-strands-agent`, `agui-langgraph-agent`) we will use as a starting point
* Standard agents: configured with `--protocol A2A` (a2a-sdk executors exist for Strands and LangGraph) or plain HTTP for simple cases
* Per-request agent construction: each request builds a fresh agent instance so Gateway MCP tool lists are scoped to the caller's identity, never a shared singleton
* Agents pull enabled skills from the skills registry at session init (see doc 04)

### 3.4 MCP Layer, Hybrid Model (recommended)

* Custom/internal MCP servers run as containers on EKS (self-hosted, open-source aligned, direct VPC access to internal systems), streamable HTTP transport, no public exposure
* AgentCore Gateway sits in front as the unified MCP endpoint for agents: it handles inbound OAuth, tool discovery and search, and converts existing REST APIs and Lambda functions into MCP tools without writing servers
* EKS-hosted MCP servers are registered as Gateway targets, SaaS APIs and Lambdas become Gateway targets directly
* Rationale: agents get one authenticated MCP endpoint with identity-scoped tools, while we keep full control and open-source freedom for custom servers. Details and trade-offs in doc 05

### 3.5 Durability, Temporal (self-hosted on EKS)

* Temporal server deployed via the official Helm chart, persistence on a dedicated PostgreSQL database in RDS, Web UI behind SSO
* Use cases: multi-step agent pipelines, retries with backoff, compensation/saga patterns, human-in-the-loop approval waits, scheduled agent jobs, fan-out across agents
* Workers written in Python live in a dedicated worker repository (per team convention), the backend only starts and signals workflows through the Temporal client, shared models come from the common contracts package. Activities call AgentCore Runtime, MCP tools, and databases
* Rule of thumb: anything that must survive a pod restart or takes longer than one HTTP request belongs in a Temporal workflow

### 3.6 Data Services

* RDS PostgreSQL (Multi-AZ): application data, agent/MCP/skill registries, chat threads and messages, Temporal persistence (separate database on the same instance initially, separate instance if load requires)
* ElastiCache (Valkey/Redis OSS compatible): session cache, rate limiting, short-lived streaming state, pub/sub if we need multi-replica SSE fan-out. This is an AWS service so it fits the "AWS where available" rule, a self-hosted Redis on EKS remains a fallback
* S3: skill bundles, user uploads, agent artifacts, exports, Temporal archival if enabled

### 3.7 Observability, CloudWatch

* EKS: Container Insights for cluster/pod metrics, Fluent Bit DaemonSet shipping logs to CloudWatch Logs, ADOT collector for application metrics and traces
* AgentCore: built-in Observability emits OTEL traces, metrics, and logs to CloudWatch GenAI Observability (sessions, traces, token usage, latency)
* Structured JSON logging everywhere with a shared correlation ID (`session_id`, `run_id`, `workflow_id`) propagated from frontend to agent to Temporal
* Dashboards and alarms per phase (see implementation plan), log retention policies to control cost

### 3.8 Authentication and Authorization, Entra ID

* SSO: OIDC against the existing Entra ID tenant, one app registration for the SPA/frontend and one for the backend API (exposed scopes), Authorization Code + PKCE
* The backend validates access tokens via the Entra JWKS endpoint, audience and issuer checks enforced
* AgentCore inbound auth: Runtime and Gateway are configured with a JWT authorizer pointing at the Entra ID OIDC discovery URL and allowed client IDs/audience, so the same user token flows end to end (frontend → backend → AgentCore)
* Authorization: prefer Entra **app roles** assigned to AD groups over raw group ID claims. Reason: the groups claim suffers from overage when a user is in many groups (the token then contains a Graph link instead of groups). App roles arrive as a clean `roles` claim. A mapping table in PostgreSQL translates roles to platform permissions (admin, agent-publisher, mcp-admin, user, etc.)
* Outbound tool auth: AgentCore Identity credential providers store OAuth clients/API keys for tools, secrets never live in agent code. Cluster-side secrets come from AWS Secrets Manager via External Secrets Operator

## 4. Key Decisions (summary)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Agent hosting | Bedrock AgentCore Runtime | Managed scaling, session isolation, native AGUI/A2A/MCP protocol support, framework-agnostic |
| 2 | Agent frameworks | Strands + LangGraph, both allowed | Both have AG-UI and A2A integrations, one frontend parser handles both |
| 3 | Agent-to-user protocol | AG-UI + CopilotKit for rich UI, generic chat for others | Decouples frontend from agent frameworks |
| 4 | Agent-to-agent / standard agents | A2A preferred, HTTP/SSE allowed | A2A is natively supported by AgentCore Runtime and both frameworks |
| 5 | MCP hosting | Hybrid: EKS containers behind AgentCore Gateway | Unified authenticated endpoint plus open-source control |
| 6 | Durability | Temporal, self-hosted on EKS | Open-source requirement, proven reliability patterns |
| 7 | Database | RDS PostgreSQL | Team choice, also serves Temporal persistence |
| 8 | Cache | ElastiCache (Valkey) | AWS-managed, Redis-compatible |
| 9 | Observability | CloudWatch end to end | Single pane for EKS and AgentCore |
| 10 | AuthN/AuthZ | Entra ID OIDC + app roles on AD groups | Reuses existing corporate identity, avoids groups-claim overage |
| 11 | Agent deployment | ARM64 container images in ECR, runtime updated via control-plane API (Phase 0 spike only: console S3 direct code deployment) | Fits existing image-based pipelines, ECR is mandatory for AgentCore container deploys |
| 12 | Toolchain | Bitbucket (SCM), Jenkins (CI/CD), Artifactory (deps/packages), Jira (tracking), Confluence (docs) | Existing corporate toolchain, applies to EKS and agent deployments alike |

Full trade-off notes and risks are in `05-decisions-risks-considerations.md`.
