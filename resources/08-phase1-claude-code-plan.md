# Phase 1 Implementation Plan for Claude Code, Platform Foundation

Execute after gate G0 passes. The rules from doc 07 section 0 apply unchanged (strict task order, verify before proceeding, [Human] tasks stop and wait, config only from environment/tfvars, pin and record versions).

Goal: real infrastructure in the corporate dev account, EKS, data services, observability, and the Jenkins/Bitbucket/Artifactory pipeline, proven by a hello-world deploy, ending at gate G1.

## Inputs [Human] before starting

* H1: Corporate AWS dev account, an IaC role Claude Code can assume (admin-like in dev), region and VPC CIDR decided
* H2: Bitbucket project created with empty repos per doc 03 section 2 (`agp-infra-terraform`, `agp-helm-charts`, `agp-jenkins-library`, `agp-lib-python`, `agp-lib-ts`, `agp-contracts`), Claude Code has push access
* H3: Jenkins controller reachable, Bitbucket webhook connectivity confirmed, an AWS deploy role for Jenkins in dev, Artifactory with pip/npm remote repos and a local repo for internal packages
* H4: Route53 hosted zone (or corporate DNS delegation) for the platform domain, ACM certificate strategy decided
* H5: Entra ID admin available for the production-grade app registrations (frontend SPA, backend API, app roles)

## Tasks

### T1, Terraform repository scaffold (`agp-infra-terraform`)

Steps: create `modules/{vpc,eks,rds,elasticache,s3,ecr,iam,observability}` and `envs/dev`, remote state backend (S3 bucket + DynamoDB lock table, [Human] confirms names), `dev.tfvars` for region/CIDR/domain, README with plan/apply usage.
Verify: `terraform init && terraform validate && terraform plan` in `envs/dev` succeeds.
Done when: plan is clean and reviewed by the human.

### T2, Core network and cluster

Steps: apply VPC (3 AZ, private/public subnets, NAT), EKS with Pod Identity enabled, managed node group (general x86) plus Karpenter for scaling, ECR repositories for the known images.
Verify: `aws eks update-kubeconfig` then `kubectl get nodes` shows Ready nodes.
Done when: cluster reachable and nodes Ready.

### T3, Cluster baseline

Steps: install via Terraform/Helm: AWS Load Balancer Controller, ExternalDNS, cert-manager, External Secrets Operator, Karpenter provisioners, create namespaces `frontend, backend, workers, mcp, temporal, observability, platform` with default-deny NetworkPolicies and explicit allows per doc 03 section 3.
Verify: all controller pods Running, a test Ingress gets an ALB and a DNS record with valid TLS.
Done when: test ingress reachable over HTTPS, then removed.

### T4, Observability baseline

Steps: install the `amazon-cloudwatch-observability` EKS add-on (Container Insights enhanced + Fluent Bit), enable CloudWatch Transaction Search once for the account (prerequisite for AgentCore GenAI Observability), set log group retention policies (start at 30 days), create a starter dashboard and alarms (node/pod health, 5xx, latency) in Terraform.
Verify: cluster metrics and a test pod's logs visible in CloudWatch, alarm test-fires via `set-alarm-state`.
Done when: dashboard populated and alarms verified.

### T5, Data services

Steps: RDS PostgreSQL Multi-AZ (databases: `app`, `temporal` created empty), ElastiCache Valkey, S3 buckets (`skills`, `artifacts`) with lifecycle rules, secrets in Secrets Manager, an ESO `ClusterSecretStore` and a smoke `ExternalSecret`.
Verify: a debug pod connects to PostgreSQL and Valkey using ESO-delivered secrets.
Done when: connectivity proven from inside the cluster, debug pod removed.

### T6, Shared Helm charts (`agp-helm-charts`)

Steps: generic app chart (deployment, service, ingress optional, HPA, SA with Pod Identity annotation, ESO refs), an `mcp-server` chart variant, Temporal values file placeholder, chart-testing lint config.
Verify: `helm lint` and `helm template` clean for both charts with example values.
Done when: charts render correctly and are tagged v0.1.0.

### T7, Jenkins shared library (`agp-jenkins-library`)

Steps: implement `vars/` steps: `ecrLogin`, `buildImage` (with `arm64` flag using buildx, native if the Jenkins agent is Graviton), `inspectorGate`, `helmDeploy`, `agentcoreUpdate` (boto3 wrapper per doc 03), `publishSkill`, `publishPackage` (Artifactory). Provide Jenkinsfile templates for each repo type (app, agent, mcp, skills, library).
[Human]: create Jenkins credentials (AWS role, Artifactory token, kubeconfig or IRSA-based access) and seed the multibranch jobs pointing at the Bitbucket repos.
Verify: a dry-run pipeline using the library passes on a scratch branch.
Done when: library tagged v0.1.0 and jobs discover branches.

### T8, Shared packages bootstrap (`agp-contracts`, `agp-lib-python`, `agp-lib-ts`)

Steps: contracts repo with initial models (agent, MCP, skill, thread, message) generating Python (pydantic) and TS (zod or types) packages, lib-python with the Entra JWT validation middleware and structured logging from Phase 0 hardened, lib-ts with the API client skeleton, each repo's Jenkinsfile publishes versioned packages to Artifactory.
Verify: `pip install` and `npm install` of the published packages from Artifactory succeed in a clean venv/project.
Done when: v0.1.0 of all three consumable from Artifactory.

### T9, Hello-world through the full pipeline

Steps: minimal FastAPI hello app in a scratch repo using the app Jenkinsfile template, pipeline builds, pushes to ECR, passes the Inspector gate, Helm-deploys to `backend` namespace in dev, exposed on the platform domain with TLS.
Verify: HTTPS endpoint answers, logs and metrics visible in CloudWatch, image digest in ECR matches the deployed pod.
Done when: gate G1 checklist from doc 02 fully green, results posted to the Jira G1 ticket [Human].

## Gate G1 mapping

Pipeline-built app reachable via ALB with TLS (T9), CloudWatch logs/metrics (T4, T9), secrets via Secrets Manager/ESO (T5), Entra sign-in unchanged from Phase 0 and app registrations production-ready (H5).
