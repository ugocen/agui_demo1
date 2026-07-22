# Architecture invariants (never break)

See root `AGENTS.md` for detail. The non-negotiables:

1. **The backend is a thin proxy.** `Phase0/backend/app/agui_proxy.py`
   SigV4-signs every AgentCore call and pipes the AG-UI SSE stream back
   **unbuffered**. Never buffer it.
2. **The agent catalog is DB-backed and AgentCore-synced. No agent id/ARN in
   env.** Agents are discovered from the AgentCore control plane and upserted
   into the platform DB; the proxy routes on the DB entry's `runtime_arn`. The
   app is **fully generic** — no per-agent backend or frontend code.
3. **Two independent auth layers.** Layer A (browser ↔ backend) via
   `AUTH_MODE` (`iam`|`entra`) — identity from the Entra/Graph token, roles
   derived from AD-group membership **server-side**, never trusted from the
   client. Layer B (backend ↔ AgentCore) is whatever the **target runtime**
   accepts, from the catalog's AgentCore-synced `inbound_auth` and never from a
   global setting: **SigV4** for an IAM-authorized runtime (the default), or the
   **caller's own Entra token** as the bearer for a JWT-authorized one. The layers
   stay independent, and a JWT agent never bypasses Layer A. See
   `Phase0/docs/IDENTITY-AWARE-AGENTS.md`.
4. **Agents deploy to AgentCore as direct-code zips, and the LLM provider is
   forked, not configured.** Each environment has exactly one provider, chosen by
   *which copy you are in*, never at runtime:
   `Phase0/agents/<a>/model_factory.py` is **Amazon Bedrock only** (no gateway
   code path; setting `BEDROCK_ENDPOINT_URL` there does nothing), and
   `cloud_deploy/agents/<a>/model_factory.py` is **gateway only** (`x-api-key`;
   no Bedrock code path; endpoint + key + model id are mandatory and it refuses to
   build without them). The env-driven switch this replaced meant one missing
   variable silently sent enterprise traffic to Bedrock, in an account with no
   Bedrock access. **`model_factory.py` is the ONLY file allowed to differ between
   the copies** — any other agent change must land in both:
   `cloud_deploy/scripts/sync_agents.sh`, then `check_agent_sync.sh` as the gate.
   Never hardcode a model id.
5. **Generative UI is A2UI, rendered generically** through the rich catalog
   (`Phase0/frontend/src/components/a2ui/richCatalog.tsx`). Adding a UI
   capability means extending that catalog, not adding per-agent React cards.
6. **The frontend is a modified Next.js 16.** Read
   `Phase0/frontend/node_modules/next/dist/docs/` before writing any Next.js
   code — see `Phase0/frontend/AGENTS.md`.
7. **`cloud_deploy/` is the enterprise side: env + the agent fork.** The backend
   and frontend live once, in `Phase0/`; `cloud_deploy/` never forks them and
   only supplies their enterprise env. The **agents are the one deliberate
   exception** (invariant 4). `win_deployed/` therefore packages backend/frontend
   from `Phase0/` and **agents from `cloud_deploy/`**.
