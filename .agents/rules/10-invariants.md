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
   client. Layer B (backend ↔ AgentCore) is **always SigV4**, independent of
   Layer A.
4. **Agents deploy to AgentCore as direct-code zips; the model provider is
   env-driven** via each agent's `model_factory.py` (default Amazon Bedrock;
   enterprise `x-api-key` gateway when both `BEDROCK_ENDPOINT_URL` and
   `BEDROCK_API_KEY` are set). Never hardcode a provider or model id.
5. **Generative UI is A2UI, rendered generically** through the rich catalog
   (`Phase0/frontend/src/components/a2ui/richCatalog.tsx`). Adding a UI
   capability means extending that catalog, not adding per-agent React cards.
6. **The frontend is a modified Next.js 16.** Read
   `Phase0/frontend/node_modules/next/dist/docs/` before writing any Next.js
   code — see `Phase0/frontend/AGENTS.md`.
7. **`cloud_deploy/` is an enterprise config overlay (env only).** The app
   lives once, in `Phase0/`.
