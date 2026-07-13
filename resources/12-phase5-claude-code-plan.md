# Phase 5 Implementation Plan for Claude Code, Production Hardening

Execute after gate G4. Doc 07 section 0 rules apply. Goal: production readiness, observability completeness, security, load, DR, cost, and onboarding, ending at gate G5 (go-live).

## Inputs [Human]

* H1: Prod AWS account ready with the same role setup as dev, prod domain and certificates, prod Entra app registrations
* H2: Load targets (concurrent users, sessions, p95 latency) and paging/on-call destination for alarms
* H3: Security review scheduling (internal or external pen test) and dependency-scanning tool choice if not already in Jenkins
* H4: Game day and restore drill date with participants

## Tasks

### T1, Production environment

Steps: create `envs/prod` in `agp-infra-terraform` reusing the modules (sized per H2), apply in the prod account, promote current-tagged images/packages/skills through the Jenkins promotion stages, prod values files in every repo, verify Entra prod registrations wired.
Verify: full stack healthy in prod, smoke suite green against prod with a pilot role.
Done when: prod mirrors dev at the same artifact digests.

### T2, Observability completion

Steps: dashboards as code (Terraform) for platform, per-agent (AgentCore GenAI Observability views, token usage, latency, error traces), per-MCP, and Temporal, alarm set with runbook links in every alarm description, log retention and trace sampling tuned per environment, correlation ID propagation audited end to end.
Verify: each alarm test-fired reaches the H2 destination, a synthetic error is traceable frontend → backend → agent → tool in CloudWatch.
Done when: on-call can diagnose the synthetic incident using dashboards alone.

### T3, Security hardening

Steps: dependency and image scanning stages enforced as blocking in the Jenkins library, NetworkPolicy audit against doc 03 namespaces, IAM least-privilege pass over all roles (Jenkins deploy, execution roles, Pod Identity), secrets rotation procedure documented, AG-UI proxy and Gateway auth abuse cases added to the test suite (token replay, wrong audience, role escalation attempts).
[Human]: run the scheduled security review, triage findings into Jira.
Verify: abuse-case tests green, scanner gates block a seeded vulnerable dependency on a scratch branch.
Done when: findings closed or risk-accepted with ADR entries.

### T4, Load and resilience testing

Steps: k6 (or Locust) scripts for concurrent SSE sessions across both agent types, ramp to H2 targets against a prod-like environment, measure AgentCore session creation behavior and first-token latency, Temporal throughput under the composite workflow, Karpenter scaling observed, fix bottlenecks found (backend replica counts, Redis fan-out, timeouts).
Verify: H2 targets met with headroom, no stream corruption at peak, results archived.
Done when: signed-off load report in Confluence [Human].

### T5, DR and game day

Steps: finalize runbooks (incident, restore, failover, AgentCore regional issue fallback), execute the restore drill in prod per H4, run the game day: injected failures (worker kill, RDS failover, ALB target drain, expired secret) handled using runbooks only.
Verify: alarms fired, runbooks sufficed, timings within H3/H2 expectations.
Done when: game day report with action items filed [Human].

### T6, Cost review

Steps: script a monthly cost snapshot (Cost Explorer API) split by tag: EKS, RDS, ElastiCache, CloudWatch ingestion, AgentCore consumption, compare against the doc 05 expectations, tune retention/sampling and instance sizing where the data says so.
Verify: report generated, top three cost drivers have an owner decision.
Done when: recurring report scheduled and first actions taken.

### T7, Developer onboarding guide

Steps: write "ship an agent / an MCP / a skill to the platform" guides (template repo usage, registry steps, RBAC, pipeline behavior, card contract rules), publish to Confluence [Human], have a developer outside the core team follow the agent guide unassisted on a sandbox agent.
Verify: the outside developer succeeds without core-team help, friction points fixed in the guide.
Done when: guide validated by that run.

### T8, Go-live

Steps: gate G5 checklist review against doc 02, pilot AD group expanded per rollout plan, hypercare window with tightened alarm thresholds for two weeks.
Done when: G5 signed off in Jira [Human], platform declared production.

## Gate G5 mapping

Load targets met (T4), alarms and runbooks proven in game day (T2, T5), restore drill passed (T5), security findings closed or accepted (T3), onboarding validated externally (T7).
