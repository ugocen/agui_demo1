# Project Status Report — Plan vs. Actual

**Date:** 2026-07-18
**Scope:** All 6 phases of the 13-document plan under `resources/` against the actual code status in `Phase0/` + `cloud_deploy/` + `win_deployed/`.
**Method:** Read the entire plan; examined the actual state of the code; ran the live health check (ruff ×2, agent-sync gate, frontend build + lint = **5/5 green**); verified open security findings individually on the code.

---

## Executive summary (one sentence)

**Phase 0 (validation spike) is complete, working, and contains much more than the plan itself — but the official G0 gate is still not fully closed (Stage B / enterprise run has not been done, several criteria open), and Phases 1–5 (the actual production platform) haven't started at all.** Also, an unplanned "enterprise delivery" pipeline (zip package v1.8.0) has emerged.

---

## What the entire plan envisioned

The plan under `resources/` means a **~3 week spike + ~17 week enterprise platform**: Next.js+CopilotKit + FastAPI on EKS, agents on Bedrock AgentCore, Temporal, RDS PostgreSQL, ElastiCache, AgentCore Gateway + MCP servers, Entra ID SSO, Jenkins/Bitbucket/Artifactory CI/CD — all with Terraform. Six phases, each with a validation gate at the end (G0–G5).

---

## Phase by phase actual status

| Phase | Plan (target) | Actual status | Rough completion |
|---|---|---|---|
| **0 — Spike** | 2 AG-UI agents, local backend+frontend, end-to-end with Entra token, Stage A (macOS) + Stage B (enterprise Win) | **Built + expanded significantly** (5 agents, DB admin catalog, generic A2UI, SSO, presentation). But G0 gate not fully signed off | **~90% done / G0 ~70% approved** |
| **1 — Infrastructure** | Terraform, EKS, RDS, ElastiCache, ECR, observability, Jenkins CI/CD | **None.** No `.tf`, no Helm, no Jenkinsfile, no k8s manifest | **0%** |
| **2 — Agent/MCP platform** | Registries (agent/MCP/skill), Gateway, MCP server on EKS, container deploy, RBAC | **Only ideas pulled forward as local prototype** (catalog DB + `/admin` + generic mount). No Gateway/MCP/skills/CI-CD | **~10% (local prototype)** |
| **3 — Data/Durability** | Temporal, persistent threads, Redis, backup/restore | **None.** Threads are still `localStorage`; DB only holds catalog+audit | **0%** |
| **4 — Multi-agent** | A2A agent, backend A2A client, composite Temporal workflow | **Only local A2A PoC** (`Phase0/a2a-poc/`, without AWS) for risk mitigation | **~5% (PoC)** |
| **5 — Production hardening** | Load testing, security, DR, cost, onboarding | **None** | **0%** |

The absence of Phase 1–5 infrastructure was verified by search: there is no `*.tf`, `Chart.yaml`, `Jenkinsfile`, or Temporal import in the repo (except `node_modules/.venv/build`).

---

## Phase 0 — detailed look

### Completed and verified

- **5 agents** live on AgentCore with zip (direct-code): `planner` (Strands), `release` (LangGraph), `bug-report`, `a2ui-demo`, `press-release` — 2 agents were requested in the plan.
- Backend AG-UI proxy (SigV4, unbuffered SSE), frontend CopilotKit v2 + **generic A2UI catalog** (a more powerful design replacing the 6 hand-written cards in the plan).
- Entra ID SSO (Microsoft Graph delegated-token method), agent catalog with DB + `/admin` screen, `ui_mode` (static/a2ui) live.
- Smoke test was **5/5 live PASS** (S1–S5) in the past; code health is **5/5 green** in this round (ruff Phase0, ruff cloud_deploy, agent-sync gate, `npm run build`, `npm run lint`).
- Two copies (Phase0 = Bedrock-only, cloud_deploy = gateway-only) in sync; drift gate is green; only `model_factory.py` differs.

### Still OPEN at the G0 gate

1. 🔴 **Stage B — enterprise account (Windows 11) run has not been done.** A core criterion for G0. `win_deployed/` (v1.8.0 zip package) is the *preparation* for this, but actual enterprise deploy + validation hasn't been confirmed.
2. 🔴 **Per-agent `required_role` is a "silent no-op"** (finding H1, re-verified in code on 2026-07-18): you restrict an agent to a role in the admin screen but `proxy_agui` in `Phase0/backend/app/agui_proxy.py` doesn't check this at all — any authorized user can invoke any agent. There is a global `REQUIRED_ROLE` gate, but no per-agent one.
3. 🟠 **Mid-flow kill / reconnect test** is still a manual/monitoring item (W1).
4. 🟠 **Full entra end-to-end** requires human-side Entra portal configuration (single-tenant, group→role mapping).

---

## Deviations from the plan

1. **Container/ECR → zip.** The plan (doc 01, decision 11) stated ECR container deploy in production; the spike intentionally switched to direct-code zip (the plan allows this). Transition to container in Phase 2 has not been done yet.
2. **6 hand-written cards → generic A2UI catalog.** The implementation pivoted to a better design (doc 13 and `Phase0/README.md` acknowledge this).
3. **An unplanned new pipeline: "enterprise delivery".** `cloud_deploy/` (LLM provider fork: enterprise agents use GenAI-marketplace gateway instead of Bedrock) + `win_deployed/` (versioned zip package for WSL2, v1.8.0). This is not in the original 6-phase plan. Effectively, the strategy seems to have shifted to: *"instead of building the whole EKS platform ourselves, deliver the validated spike as a zip to the organization's closed intranet."* A legitimate pivot, but not officially aligned with the plan.

---

## Open risks / security

- 🔒 **`cloud_deploy/agents/.env` is still on disk** (finding M8). The audit stated it contained a real gateway API key and should be **rotated and deleted** — the file is still there (content not opened/read).
- **H1** (above) — seemingly configured but non-functional security check.
- **M2** — unknown `AUTH_MODE` is still "fail-open" (falls back to iam); `Phase0/backend/app/auth.py` degrades unknown mode to iam with a warning.
- Minor drift in docs (e.g. `Phase0/ARCHITECTURE.md` says "3 runtimes" / old SPA client id while there are actual 5 agents / new `agui-test` client).

Note: Some findings in the audit were later closed — H2 (CopilotKit runtime singleton) and M7 (`ui_mode` dead space) were fixed with PR #31; for M9 (clean error when credentials expire) the proxy can now return 503.

---

## Net conclusion

We have proven the riskiest and newest integration (AG-UI + AgentCore + CopilotKit + Entra) — and did much more than the plan required. However:

- Phase 0 is **not officially closed**: Stage B enterprise run + H1 role enforcement + kill test are missing.
- **Not a single brick of the production platform (Phases 1–5) has been laid** — EKS/Temporal/RDS/Gateway/CI-CD are completely absent.
- Effectively, energy has shifted from the "move to Phase 1" path to **maturing the spike + enterprise zip delivery**.

Summary: *"The spike is finished and solid; but neither is G0 officially signed off nor has the actual platform started."*
