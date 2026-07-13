# Phase 3 Implementation Plan for Claude Code, Data and Durability

Execute after gate G2. Doc 07 section 0 rules apply. Goal: Temporal-backed reliability and persistent conversations, ending at gate G3.

## Inputs [Human]

* H1: Empty Bitbucket repo `agp-temporal-workers`
* H2: Approval for the Temporal server version to pin (official Helm chart), and confirmation the Temporal Web UI stays internal behind SSO
* H3: RPO/RTO expectations for dev/prod to size the backup tasks

## Tasks

### T1, Temporal server on EKS

Steps: deploy the official Temporal Helm chart into the `temporal` namespace using values in `agp-helm-charts` (persistence pointed at the `temporal` database on RDS PostgreSQL, no bundled Cassandra/Elastic in dev), internal ingress for the Web UI behind `oauth2-proxy` with Entra ID, Terraform for the extra DB user/grants.
Verify: `temporal` CLI health checks pass from a debug pod, Web UI reachable only after Entra sign-in.
Done when: server healthy and persisted in RDS.

### T2, Worker repository (`agp-temporal-workers`)

Steps: scaffold with `agp-lib-python` + `agp-contracts`, worker entrypoint per task queue, Dockerfile, app Jenkinsfile, Helm values deploying to the `workers` namespace, settings for Temporal address and namespace via ESO.
Verify: worker pod connects and polls its task queue (visible in Web UI).
Done when: pipeline-deployed worker polling in dev.

### T3, First workflows

Steps: implement three workflows with activities that call the backend/AgentCore: `agent_pipeline` (multi-step agent task with retry policy and backoff), `hitl_approval` (waits on a signal delivered by a backend endpoint, timeout with escalation activity), `scheduled_report` (Temporal Schedule invoking the planner agent daily in dev). Backend gets thin start/signal/query endpoints using the Temporal client, RBAC-guarded.
Verify: each workflow runs green in the Web UI, retry visibly triggers on an injected activity failure.
Done when: all three demonstrable in dev.

### T4, Thread and message persistence

Steps: Alembic migration for `threads` and `messages` per doc 03 section 5, backend persists AG-UI conversation turns and run metadata (`run_id`, `workflow_id` correlation), frontend history view (list threads, reopen a thread, resume an in-flight run after reload).
Verify: chat survives backend pod restart and browser reload, an old thread reopens with full history.
Done when: persistence proven under pod restart.

### T5, Redis integration

Steps: use ElastiCache Valkey for per-user rate limiting middleware, session-scoped cache (skills bundles, registry lookups), and pub/sub relay so SSE streams survive multiple backend replicas, scale backend to 2 replicas in dev.
Verify: streaming works with 2 replicas behind the ALB, rate limit returns 429 past the threshold.
Done when: multi-replica streaming stable.

### T6, Backup and restore

Steps: enable and tag automated RDS snapshots per H3, S3 lifecycle policies for skills/artifacts, write the restore runbook (docs + Confluence [Human]), execute one dev restore drill into a scratch instance and point a scratch backend at it.
Verify: restored data readable, drill timing recorded against RTO.
Done when: drill documented with timings.

### T7, G3 chaos checks

Steps: scripted checks: kill a worker pod mid `agent_pipeline` (workflow resumes and completes), let `hitl_approval` wait 60+ minutes then approve (completes), kill a backend pod mid-stream (frontend reconnects, thread intact). Add to the regression suite where automatable.
Done when: gate G3 checklist green and posted to Jira [Human].

## Gate G3 mapping

Worker-kill resume (T7), long HITL wait (T3, T7), history surviving restarts and re-login (T4).
