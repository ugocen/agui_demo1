# MCP Server Management and Shared Skills

## Part A, MCP Servers

### A.1 Hosting Model (recommended: hybrid)

* Custom/internal MCP servers run as containers on EKS in the `mcp` namespace, one Deployment per server, shared Helm chart, streamable HTTP transport, ClusterIP only (never public)
* AgentCore Gateway is the single MCP endpoint agents talk to. It provides inbound OAuth, tool discovery and semantic tool search, and can turn existing REST APIs (OpenAPI) and Lambda functions into MCP tools without writing a server
* EKS-hosted servers are registered as Gateway MCP targets. Pure API integrations (SaaS, internal REST) go straight into Gateway as OpenAPI/Lambda targets, no container needed
* Direct connection from an agent to an EKS MCP endpoint is allowed as an exception for latency-critical internal tools, documented per case in the registry

Why hybrid: agents get one authenticated, identity-scoped endpoint (Gateway), we keep open-source control and VPC data access for custom logic (EKS), and we avoid writing servers for plain API wrapping (Gateway targets).

Networking note to validate in Phase 2: Gateway targets must be reachable from Gateway. Expose EKS MCP services to Gateway via an internal mechanism (private ALB reachable from AgentCore, or VPC connectivity as supported in our region). This is a G2 checklist item.

### A.2 Building an MCP Server

* Python: FastMCP with streamable HTTP. TypeScript: official MCP SDK. Keep one server per bounded domain (e.g., `internal-tools`, `hr-data`), not one giant server
* Standard skeleton from the `agp-mcp-template` repository: health endpoint, structured JSON logging with correlation IDs, OTEL instrumentation to ADOT, config via env vars, secrets via External Secrets Operator
* Tool design rules: explicit input/output schemas, idempotent where possible, no destructive default behavior, pagination for list tools

### A.3 Lifecycle

* Develop: PR in the server's own repository (`agp-mcp-<name>`), contract tests assert tool schemas so agents do not break silently
* Deploy: CI builds image to ECR, Helm deploy to `mcp` namespace
* Register: entry in the MCP registry (Postgres + admin UI) with owner, allowed roles, endpoint, then a Gateway target is created/updated (Terraform-managed)
* Version: semver image tags, breaking tool schema changes require a new tool name or major version, canary by deploying `name-v2` alongside `name`
* Monitor: registry health checks against Gateway targets, CloudWatch alarms on error rate/latency per server
* Retire: mark deprecated in registry, alert owning agents, remove target after a grace period

### A.4 Security

* Inbound: Gateway JWT authorizer configured with Entra ID, tools are scoped per caller identity, agents are built per request so each user sees only permitted tools
* Outbound: credentials for downstream systems live in AgentCore Identity credential providers or Secrets Manager, never in code or images
* Authorization: `required_roles` on each MCP registry entry, enforced both at the platform API and reflected in Gateway target policy where supported
* Network: `mcp` namespace has NetworkPolicies allowing ingress only from the backend and the Gateway path, egress limited to declared dependencies

## Part B, Shared Skills

### B.1 What a Skill Is Here

A skill is a versioned, reviewable bundle of reusable agent capability that is not code baked into an agent image:

```
skills/report-writing/
├── manifest.yaml     # name, version, description, required MCP tools, allowed roles
├── SKILL.md          # instructions injected into the agent's context
└── resources/        # templates, examples, small reference files
```

Skills carry instructions, prompts, tool-usage recipes, and reference resources. Heavier shared *code* belongs in the `agp-lib-python` package (published to Artifactory), not in skills.

### B.2 Where Skills Live

* Source of truth: the dedicated `agp-skills` repository, changed via PR (review, history, ownership)
* Distribution: CI validates the manifest against the schema and publishes a versioned tarball to the skills S3 bucket (`s3://.../skills/report-writing/1.2.0.tar.gz`), and upserts a row in the `skills` registry table
* Never let agents read skills straight from git at runtime, S3 + registry gives immutability, versioning, and fast reads

### B.3 How Skills Are Activated

* The registry holds `agent_skills(agent_id, skill_id, enabled, pinned_version)`, managed from the admin UI, guarded by the `skill-admin` role
* Each agent includes the small `skills_loader` library. At session init it asks the registry "which skills are enabled for me", downloads missing bundles from S3, and caches them (memory or Redis, keyed by skill+version)
* Progressive disclosure: the loader injects only skill names and descriptions into the system context, the full `SKILL.md` body is loaded when the agent decides the skill is relevant, keeping token usage flat as the catalog grows
* Enabling, disabling, or upgrading a skill therefore requires no agent redeploy, new sessions pick it up immediately
* The manifest's `required_tools` list is checked at load time against the tools the agent actually received from Gateway, missing tools disable the skill with a logged warning instead of failing the session

### B.4 Governance

* Semver, changelog entry required per skill release
* A skill declaring `allowed_roles` is only served to sessions whose user holds one of those roles
* Contract tests in CI: manifest schema, referenced tools exist in the MCP registry, resource size limits
* Quarterly review of low-usage skills (usage metrics from loader telemetry in CloudWatch)
