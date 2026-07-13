# Project Structure, Repository and Cluster Layout

## 1. Repository Strategy (multi-repo)

Following the team's existing convention, each deployable unit lives in its own Bitbucket repository with its own Jenkinsfile at the repo root, loaded by Jenkins from SCM. What a monorepo gives for free (shared contracts, atomic changes) is provided here by versioned internal packages in Artifactory and by template repositories, so discipline on package versioning is the price of this model and is called out below.

## 2. Repository Layout

All repos under one Bitbucket project, common name prefix (`agp-` used as an example, adjust to your naming convention).

Core application repos:

* `agp-frontend`, Next.js + CopilotKit
* `agp-backend`, FastAPI (API, registries, AG-UI proxy, A2A client)
* `agp-temporal-workers`, Temporal workflows, activities, and worker entrypoints (separate from the backend per team convention, the backend only starts and signals workflows through the Temporal client)

Per-component repos, created from template repos:

* `agp-agent-<name>`, one repo per agent, created from `agp-agent-template`
* `agp-mcp-<name>`, one repo per MCP server, created from `agp-mcp-template`

Shared and platform repos:

* `agp-skills`, single repo holding all skill bundles (skills are small content folders, one repo per skill would be overhead without benefit)
* `agp-lib-python` and `agp-lib-ts`, shared libraries (auth, logging, registry client, AG-UI helpers, skills loader), published as versioned packages to Artifactory and consumed with pinned versions everywhere
* `agp-contracts`, API and event schemas (registry API models, chat message shapes) generating both Python and TS packages, the single source of truth between frontend, backend, workers, and agents
* `agp-infra-terraform`, all Terraform (modules + `envs/{dev,prod}`)
* `agp-helm-charts`, shared base charts (generic app chart, MCP server chart, Temporal chart values), service repos carry only their `values-{env}.yaml`
* `agp-jenkins-library`, the Jenkins shared library (ECR login, ARM64 build, Helm deploy, AgentCore runtime update, skill publish steps)

Key repo internals:

```
agp-frontend/                      agp-backend/
├── src/app/                       ├── app/api/        # routers
├── src/components/agents/         ├── app/auth/       # JWT, RBAC
├── src/components/chat/           ├── app/agui/       # AG-UI proxy
├── src/lib/auth/                  ├── app/a2a/        # A2A client
├── Dockerfile                     ├── app/registry/
└── Jenkinsfile                    ├── app/db/         # models, Alembic
                                   ├── Dockerfile
agp-temporal-workers/              └── Jenkinsfile
├── workflows/
├── activities/                    agp-agent-template/
├── workers/          # entrypoints├── agent.py        # + skills_loader use
├── Dockerfile                     ├── Dockerfile      # linux/arm64
└── Jenkinsfile                    ├── values-{env}.yaml
                                   └── Jenkinsfile     # ECR + runtime update
agp-skills/
├── _schema/manifest.schema.json   agp-mcp-template/
├── report-writing/                ├── server.py       # FastMCP, HTTP
│   ├── manifest.yaml              ├── Dockerfile
│   ├── SKILL.md                   ├── values-{env}.yaml
│   └── resources/                 └── Jenkinsfile
└── Jenkinsfile
```

Multi-repo working rules:

* Breaking changes to `agp-contracts` or the lib packages require a major version bump, consumers upgrade explicitly via PR, never floating versions
* Template repos are versioned too, a lightweight script (or Bitbucket repo template feature) stamps new agent/MCP repos and registers the Jenkins job
* Cross-repo features are coordinated in Jira with linked stories per repo, the platform decision log in Confluence records contract version bumps


## 3. EKS Layout

Namespaces per concern, network policies between them:

* `frontend`, Next.js + CopilotKit runtime
* `backend`, FastAPI API
* `workers`, Temporal workers (deployed from `agp-temporal-workers`)
* `mcp`, all MCP server deployments (one Deployment per server, shared Helm chart)
* `temporal`, Temporal server, Web UI
* `observability`, ADOT collector, Fluent Bit (DaemonSet), exporters
* `platform`, ingress controller, external-secrets, cert-manager, ExternalDNS

Ingress: one ALB for the frontend and backend API (public/internal per policy), MCP servers and Temporal stay internal (ClusterIP, no public exposure), Temporal Web UI behind SSO on an internal ingress.

## 4. Environments

* Recommended: separate AWS accounts for dev and prod (test optional in between), each with its own EKS cluster, RDS, Gateway, and AgentCore runtimes
* AgentCore resources are named per environment (`{agent}-{env}`), registries in each environment only reference runtimes in the same account
* Entra ID: separate app registrations per environment, same tenant

## 5. Data Model Sketch (PostgreSQL)

* `agents(id, name, description, protocol[agui|a2a|http], runtime_arn, ui_capability, required_roles[], status, owner, created_at, ...)`
* `mcp_servers(id, name, transport, endpoint, gateway_target_id, required_roles[], health_status, owner, ...)`
* `skills(id, name, version, s3_uri, manifest_json, status)`
* `agent_skills(agent_id, skill_id, enabled, pinned_version)`
* `threads(id, user_id, agent_id, created_at)` and `messages(id, thread_id, role, content_json, run_id, created_at)`
* `role_permissions(role, permission)` mapping Entra app roles to platform permissions
* Temporal uses its own dedicated database on the same RDS instance

## 6. CI/CD Flow (Bitbucket + Jenkins + Artifactory)

Toolchain roles:

* Bitbucket hosts all platform repositories under a single project, branch permissions and PR merge checks require green Jenkins builds
* Jenkins runs all pipelines as pipeline-as-code: each repository carries one Jenkinsfile at its root, and Jenkins jobs are configured as "Pipeline script from SCM" (or multibranch discovery) pointing at it. No pipeline logic lives in the Jenkins UI, changes to pipelines go through PR review like any other code. Builds are triggered by Bitbucket webhooks, common steps come from the `agp-jenkins-library` shared library so per-repo Jenkinsfiles stay short and uniform
* Artifactory serves as the dependency proxy (pip and npm remote repositories) and hosts the internal packages from `agp-lib-python`, `agp-lib-ts`, and `agp-contracts`. Runtime container images live in ECR, which is mandatory for AgentCore (Runtime only pulls from ECR) and keeps EKS pulls consistent. Artifactory can additionally mirror images for retention if policy requires
* Jenkins authenticates to AWS with a dedicated deploy role per environment (least privilege: ECR push, EKS deploy, `bedrock-agentcore-control` for runtime updates, S3 skill bucket write)

Pipeline stages by repo type (each defined in that repo's Jenkinsfile via shared-library steps):

* All repos, PR stage: lint, unit tests, contract tests against pinned `agp-contracts` versions, dependency resolution through Artifactory
* EKS app repos (frontend, backend, temporal-workers, MCP servers): build image, push to ECR, ECR enhanced scanning (Amazon Inspector) as a gate, Helm deploy to dev using the shared chart from `agp-helm-charts` plus the repo's `values-dev.yaml`
* Agent repos: build **linux/arm64** image (AgentCore Runtime requires ARM64), push to ECR, Inspector scan gate, then `create_agent_runtime` or `update_agent_runtime` via the `bedrock-agentcore-control` API (shared-library step wrapping boto3), smoke test with a test invocation. ARM64 builds need either Graviton-based Jenkins build agents (recommended, native speed) or `docker buildx` with QEMU emulation (slower)
* Skills repo: validate manifests, package tarballs, publish to the skills S3 bucket, upsert registry rows
* Library and contracts repos: build, test, publish versioned packages to Artifactory
* Promotion to prod: git tag in the repo triggers promotion of the **same** image digest or package version (no rebuild), manual approval stage in Jenkins
* Terraform repo: plan/apply job per environment with plan review before apply

Reference implementation: the official `aws-samples/sample-bedrock-agentcore-runtime-cicd` repository demonstrates exactly this build → ECR → Inspector → create/update runtime flow (with GitHub Actions as the orchestrator), its boto3 deploy/test/cleanup scripts port directly into our Jenkins pipelines.

## 7. Process and Documentation Tooling

* Jira: one epic per implementation phase, validation gates tracked as milestone tickets with the gate checklist as acceptance criteria, agents/MCPs/skills shipped by feature teams enter as stories under a platform intake board
* Confluence: documentation home. These project documents become the initial Confluence space structure (Architecture, Implementation Plan, Project Structure, MCP and Skills, Decision Log). ADRs are maintained as Confluence pages using the condensed format from doc 05, runbooks live in the same space and are linked from CloudWatch alarm descriptions
* Keep in-repo docs limited to developer-facing content that must version with that repo's code (READMEs, contribution guide, template usage), Confluence holds the living project documentation
