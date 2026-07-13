# Decisions, Risks, and Considerations

## 1. Decision Records (condensed ADRs)

### ADR-1, MCP hosting: hybrid (EKS containers behind AgentCore Gateway)

* Options: (A) everything on Gateway targets only, (B) everything self-hosted on EKS with agents connecting directly, (C) hybrid
* A alone fails for custom logic needing VPC data access and open-source control. B alone loses unified auth, identity-scoped tool lists, and tool discovery, and forces every agent to manage N endpoints
* Chosen: C. Consequence: one extra hop through Gateway for EKS tools (acceptable latency for tool calls), and we must validate Gateway-to-EKS network reachability early (G2 item)

### ADR-2, Standard-agent protocol: A2A preferred, HTTP/SSE allowed

* A2A is natively supported by AgentCore Runtime and by Strands/LangGraph executors, gives us agent cards, task semantics, and future agent-to-agent interop for free
* Plain HTTP/SSE remains permitted for trivial agents where A2A ceremony adds no value, the registry `protocol` field keeps both first-class

### ADR-3, PostgreSQL on RDS

* Team decision. Also serves Temporal persistence (supported first-class) and the registries. Start Multi-AZ, single instance with separate logical databases, split Temporal out to its own instance if load requires

### ADR-4, Self-hosted Temporal and self-hosted CopilotKit

* Matches the open-source preference. Cost: we own upgrades, scaling, and the gaps the hosted versions fill (notably CopilotKit premium features like thread persistence, we build that on PostgreSQL ourselves)
* Watch item: CopilotKit also offers a licensed "Enterprise Intelligence Platform" that is self-hostable on Kubernetes via a Helm chart and provides threads/persistence out of the box. If our own persistence work in Phase 3 proves expensive, this is a paid escape hatch worth re-evaluating (it would be a licensed product, not open source)

### ADR-5, Entra ID app roles over raw group claims

* Group-claim overage (users in many groups get a Graph link instead of groups in the token) makes raw group IDs fragile. App roles assigned to AD groups arrive as a clean `roles` claim and decouple token content from directory sprawl
* AD group changes still drive access (groups are assigned to app roles), satisfying the "AD groups limit what people can do" requirement

## 2. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| AG-UI is a young (2025) protocol, FAST templates are reference quality, not hardened | Core UX bet could underdeliver | Phase 0 spike with explicit G0 kill-switch decision, fallback is generic SSE chat for all agents |
| Open-source CopilotKit lacks thread persistence and concurrent-request handling per thread | Broken UX at scale | We own persistence in PostgreSQL (Phase 3), add per-thread locking/queueing in the backend, load test in Phase 5 |
| Gateway-to-EKS target reachability (private connectivity) may constrain the hybrid MCP model | MCP architecture rework | Validate in Phase 2 week 1, fallback options: private ALB exposure, or direct agent-to-MCP for affected servers |
| Entra ID as JWT authorizer for AgentCore inbound auth (docs and samples lean on Cognito) | Auth rework in Phase 0 | Test in the first week of Phase 0, fallback: backend exchanges the Entra token and calls AgentCore with SigV4 while keeping user identity in request context |
| Temporal operational burden (upgrades, schema migrations, scaling) | Ops load on a small team | Official Helm chart, pinned upgrade cadence, runbooks, RDS-backed persistence keeps state safe |
| CloudWatch cost growth (log ingestion, GenAI traces) | Budget surprise | Retention policies from day one, sampling on traces, monthly cost review in Phase 5 checklist |
| AgentCore regional availability and quotas | Deployment constraints | Confirm target region supports Runtime AGUI/A2A protocols and Gateway before Phase 1 Terraform is finalized |
| AgentCore Runtime requires linux/arm64 images, current Jenkins agents may be x86-only | Broken or slow agent builds | Provision Graviton-based Jenkins build agents, interim fallback is `docker buildx` with QEMU emulation, validate build times in Phase 1 |
| Per-request agent construction adds cold-path latency | Slower first token | Measure in Phase 0, cache expensive constructions (model clients, skill bundles), keep identity-scoped parts per request |
| Skills loaded at runtime could drift from tools available | Silent capability loss | Loader validates `required_tools` and logs/disables, contract tests in CI |

## 3. Open Questions to Resolve Early

* Target AWS region(s), and confirmation that AgentCore Runtime (with AGUI and A2A protocol support) and Gateway are available there
* Model access: which Bedrock models the agents will use, quota requests
* Data classification: which internal systems MCP servers may touch, any data residency constraints
* Environment count and account structure (recommendation in doc 03: separate dev/prod accounts)
* Team ownership: who owns platform vs. who ships agents onto it, this drives the RBAC role list
* Expected concurrency (users, simultaneous sessions) for sizing and load-test targets

## 4. Cost Notes (order-of-magnitude thinking, not a quote)

* AgentCore is consumption-based (Runtime seconds, Gateway calls, Memory, Observability), cheap at pilot scale, watch it after rollout
* Fixed-ish monthly base: EKS control plane(s), node groups, RDS Multi-AZ, ElastiCache, ALB, NAT
* Self-hosted Temporal and CopilotKit cost engineer time instead of license fees, that is the trade we chose deliberately
* CloudWatch ingestion is the classic silent grower, retention and sampling policies are in the Phase 1 and 5 checklists

## 5. General Thoughts

* The single truly novel integration is AG-UI + AgentCore + CopilotKit + Entra ID together. Everything else (EKS, FastAPI, Temporal, RDS) is well-trodden. That is why Phase 0 exists and why its gate has an explicit fallback decision
* The registry-driven design (agents, MCPs, skills all as data) is the main product idea: adding a capability should be a registration, not a frontend release
* Keep agents thin: business durability in Temporal, tools in MCP, reusable knowledge in skills, so agents stay swappable across frameworks
* Write the decision log as you go, the condensed ADR format above is enough
