# Phase 2 Implementation Plan for Claude Code, Agent and MCP Platform

Execute after gate G1. Doc 07 section 0 rules apply. Goal: the registry-driven core product, agents and MCP servers and skills managed as data, ending at gate G2.

## Inputs [Human]

* H1: Decision on the platform roles list (admin, agent-publisher, mcp-admin, skill-admin, user) and the AD groups mapped to each Entra app role
* H2: Empty Bitbucket repos: `agp-backend`, `agp-frontend`, `agp-agent-template`, `agp-mcp-template`, `agp-skills`, plus the first real repos `agp-agent-sdlc-planner`, `agp-agent-release-readiness`, `agp-mcp-internal-tools`
* H3: Confirmation of the Gateway-to-EKS connectivity approach for MCP targets (internal ALB reachable by Gateway, or the region's supported private connectivity), this is the G2 week-1 validation item from doc 05

## Tasks

### T1, Backend service (`agp-backend`)

Steps: port the Phase 0 backend into the repo using `agp-lib-python` and `agp-contracts`, add Alembic migrations for `agents`, `mcp_servers`, `skills`, `agent_skills`, `role_permissions` (doc 03 section 5), CRUD routers with RBAC per role from H1, health/readiness endpoints, Dockerfile, Jenkinsfile (app template), Helm values.
Verify: pipeline deploys to dev, OpenAPI docs reachable, CRUD works via authenticated requests, RBAC denies a user lacking the role.
Done when: registry APIs live in dev behind Entra auth.

### T2, Frontend catalog (`agp-frontend`)

Steps: port the Phase 0 frontend, add the agent catalog page driven by `GET /api/agents`, dynamic mounting (CopilotKit surface when `capability=agui`, placeholder chat screen otherwise), admin pages for the three registries gated by roles, Jenkinsfile, Helm values.
Verify: deployed to dev, catalog lists registered agents, admin pages enforce roles.
Done when: catalog-driven UI live in dev.

### T3, Agent template and promoted agents

Steps: build `agp-agent-template` (agent skeleton, skills loader stub, ARM64 Dockerfile per the runtime contract, agent Jenkinsfile calling `buildImage(arm64)` + `agentcoreUpdate`, values per env). Create the two real agent repos from it and port the Phase 0 planner (Strands) and release (LangGraph) agents. Deploy both through Jenkins as container images to AgentCore (the production path replacing the Phase 0 zip deploys), register both in the agent registry.
Verify: both runtimes READY from pipeline deploys, both usable end to end from the dev frontend, adding a registry entry requires no frontend change.
Done when: Phase 0 zip runtimes retired, container runtimes serving.

### T4, AgentCore Gateway

Steps: Terraform module for the Gateway with Entra ID JWT inbound auth, one Lambda or OpenAPI target as the first tool source, wire the planner agent to fetch its tool list from the Gateway per request (identity-scoped construction per doc 01).
Verify: agent lists and calls a Gateway tool, a user without the required role sees a reduced tool list.
Done when: Gateway is the agents' single MCP endpoint.

### T5, First MCP server (`agp-mcp-internal-tools`)

Steps: build from `agp-mcp-template` (FastMCP, streamable HTTP, health endpoint, OTEL, ESO secrets), deploy to the `mcp` namespace via its Jenkinsfile, expose internally per H3, register as a Gateway MCP target via Terraform, add the registry entry with `required_roles` and health checks.
Verify: an agent invokes a tool on this server through the Gateway, registry health check green, NetworkPolicy blocks direct access from other namespaces.
Done when: EKS-hosted MCP reachable through Gateway (or the documented fallback from doc 05 is adopted and recorded as an ADR).

### T6, Skills platform (`agp-skills` + loader)

Steps: skills repo with the manifest schema and one real skill (e.g., `report-writing` used by the planner), Jenkinsfile validating and publishing versioned bundles to the skills S3 bucket and upserting registry rows, implement the `skills_loader` in `agp-lib-python` (fetch enabled skills at session init, cache, progressive disclosure, `required_tools` check per doc 04), enable the skill for the planner via the admin UI.
Verify: toggling the skill changes planner behavior on a fresh session without redeploying the agent, disabling reverts it.
Done when: skill lifecycle works end to end from PR to activation.

### T7, G2 regression run

Steps: extend `smoke_test.py` into a small pytest suite covering: register-new-agent flow, Gateway tool call with identity scoping, skill toggle behavior, RBAC denials. Wire it as a post-deploy stage in the backend Jenkinsfile against dev.
Done when: suite green in the pipeline, gate G2 checklist posted to Jira [Human].

## Gate G2 mapping

New agent onboarded end to end without frontend changes (T3), Gateway-scoped MCP tool call (T4, T5), skill enable/disable without agent redeploy (T6).
