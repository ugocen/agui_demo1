# Official Resources and References

Curated, verified official sources per component, with notes on what to take from each. Team members should treat these as the baseline before any blog post or third-party tutorial.

## 1. Amazon Bedrock AgentCore

* Developer Guide, AG-UI on Runtime: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui.html
  The protocol contract we build against: containers on port 8080, `/invocations` for HTTP/SSE and `/ws` for WebSocket, runtime deployed with the AGUI protocol flag, AgentCore acting as an authenticated proxy. Includes Strands (`ag-ui-strands`) and TypeScript examples
* Developer Guide, direct code deployment overview: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy.html
  Zip-based deployment concept and the official comparison against containers: 250 MB zip limit vs 2 GB images, faster subsequent updates, higher session creation rate (25/s vs 1.6/s), automatic runtime patching by AWS. Our Phase 0 spike path
* Developer Guide, direct code deployment for Python: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy-python.html
  The concrete recipe behind our Phase 0 procedure: entrypoint requirements (`@app.entrypoint` or `/invocations` + `/ping`), ARM64 dependency packaging, zip structure and POSIX permissions, 250 MB zipped / 750 MB unzipped limits, console deploy steps (Host Agent → S3 source → Create Endpoint → Test Endpoint), execution role permissions
* Developer Guide, direct code deployment troubleshooting: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-code-deploy-common-issues.html
  The failure catalog for the spike: missing `s3:GetObject` on the caller role, `kms:Decrypt` for CMK-encrypted buckets, ARM64 binary validation failures and the `--python-platform aarch64-manylinux2014` fix, entrypoint path mismatches
* Developer Guide, deploy without the CLI (our production path): https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html
  The official recipe for our ECR-based deployment: build a linux/arm64 image, push to ECR, then `create_agent_runtime` with `containerUri` via the `bedrock-agentcore-control` boto3 client. Also documents the `/invocations` + `/ping` agent contract and lifecycle settings
* Developer Guide, Observability getting started: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-get-started.html
  One-time CloudWatch Transaction Search enablement per account, runtime-hosted vs. non-runtime agent instrumentation (ADOT SDK), session ID correlation via OTEL baggage, GenAI Observability dashboard usage
* Samples repository (tutorials, use cases, integrations): https://github.com/awslabs/amazon-bedrock-agentcore-samples
  `01-tutorials` for each primitive (Runtime, Gateway, Memory, Identity), `02-use-cases` including an A2A multi-agent incident response example, `03-integrations` including an **Entra ID inbound auth** integration, directly relevant to our Phase 0 auth work
* Samples repository, AgentCore CLI era: https://github.com/awslabs/agentcore-samples
  Newer samples plus production-ready IaC templates (CloudFormation, CDK, Terraform) for provisioning AgentCore resources, useful for our Terraform module
* FAST, Fullstack Solution Template for AgentCore: https://github.com/awslabs/fullstack-solution-template-for-agentcore
  Reference implementation of the AG-UI patterns (`agui-strands-agent`, `agui-langgraph-agent`) with a single frontend parser. We mine patterns from it, we do not deploy it as-is (it is CDK + Cognito + Amplify, our stack is EKS + Entra ID + ECR). AWS itself labels it a proof-of-value, not a hardened production baseline
* Python SDK (`bedrock-agentcore` on PyPI): https://pypi.org/project/bedrock-agentcore/
  `serve_ag_ui` and `AGUIApp` helpers for AG-UI servers, `serve_a2a` with framework executors (Strands, LangGraph) for our standard agents
* Official CI/CD reference: https://github.com/aws-samples/sample-bedrock-agentcore-runtime-cicd
  Demonstrates build → push ECR → Amazon Inspector scan gate → create/update runtime via boto3, with IAM role scripts and integration tests. Orchestrated with GitHub Actions there, the boto3 scripts port directly into our Jenkins pipelines
* AWS blog, AG-UI generative UI on AgentCore: https://aws.amazon.com/blogs/machine-learning/build-generative-ui-for-ai-agents-on-amazon-bedrock-agentcore-with-the-ag-ui-protocol/
  Walkthrough of FAST AG-UI patterns plus the CopilotKit sample (generative UI, shared state, HITL), the closest official end-to-end match to our Phase 0

## 2. CopilotKit and AG-UI

* Main repository: https://github.com/CopilotKit/CopilotKit
  MIT-licensed monorepo, the self-hosted `@copilotkit/runtime` package, React hooks (`useAgent`, generative UI, shared state, HITL)
* Self-hosting guide: https://docs.copilotkit.ai/guides/self-hosting
  How to run the Copilot Runtime on our own backend, register agents, and connect AG-UI agents. Important production note from the docs: direct agent connections (`agents__unsafe_dev_only`) are dev-only, production self-managed AG-UI connections must use the `selfManagedAgents` prop with authentication handled by us, this is exactly our backend-proxy design
* AG-UI integrations index: https://docs.ag-ui.com/integrations
  Official list of framework and client integrations, confirms AgentCore as a first-class deployment target
* Strands AG-UI integration guide: https://strandsagents.com/docs/community/integrations/ag-ui/
  Building AG-UI chat experiences with Strands + CopilotKit and deploying to AgentCore, note the Strands docs flag the AG-UI package as community-maintained, review it before production use (already captured as a Phase 0 risk)

## 3. CloudWatch (EKS and platform observability)

* Container Insights on EKS overview: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/deploy-container-insights-EKS.html
  The two supported approaches (OTel Container Insights, recommended, and Enhanced/Classic), both via the `amazon-cloudwatch-observability` EKS add-on
* CloudWatch Observability EKS add-on quick start: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-setup-EKS-addon.html
  One add-on installs the CloudWatch agent (infrastructure metrics), Fluent Bit (container logs), and Application Signals, supports EKS Pod Identity for permissions. This replaces our earlier plan of separately managed Fluent Bit
* Enhanced observability metrics reference: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-metrics-enhanced-EKS.html
  Full metric/dimension list in the `ContainerInsights` namespace, notes the per-observation pricing model, input for our dashboard and alarm design

## 4. How to Use These Sources Per Phase

* Phase 0: AG-UI Runtime doc + direct code deployment guides (console + S3 path) + FAST AG-UI patterns + `03-integrations` Entra ID example + CopilotKit self-hosting guide (`selfManagedAgents`)
* Phase 1: deploy-without-CLI doc + CI/CD sample repo (Jenkins port) + CloudWatch add-on quick start + Transaction Search enablement
* Phase 2: AgentCore samples `01-tutorials` for Gateway and Identity, Terraform templates from `agentcore-samples`
* Phase 3 and 4: `serve_a2a` in the Python SDK, the A2A multi-agent use case in `02-use-cases`
* Temporal (self-hosted) and its Helm chart are documented at the Temporal project's official site and GitHub organization, adopt the official Helm chart and pin versions, avoid unofficial charts

## 5. Working Rules

* Official AWS docs and awslabs/aws-samples repos take precedence over blogs when they conflict
* Every external pattern we adopt gets a line in the Confluence decision log naming the source and version/commit consulted
* Sample repos (marked experimental/educational by AWS) are pattern sources, not dependencies, we copy and own the code we take
* Re-verify fast-moving pieces (AG-UI packages, AgentCore protocol flags, CopilotKit runtime API) at the start of each phase, this space changed materially within the last twelve months
