# AWS access policy and facts

- Account `122524101917`, region `us-east-1`.
- Deploy bucket: `agui-demo1-deploy-122524101917`.
- Runtime execution role: `agui-demo1-runtime-exec`.
- IAM setup (deployer user policy, execution role trust + policy) lives under
  `Phase0/aws-setup/`. Run once via the `aws-bootstrap` workflow.
- **No agent id or runtime ARN ever goes in env.** The agent catalog is
  DB-backed and populated purely by syncing the AgentCore control plane
  (`list_agent_runtimes` / `get_agent_runtime`); the backend proxy routes on
  the DB entry's ARN. See invariant 2 in `10-invariants.md`.
- **Deploy config (bucket / execution role / model id) is not read from
  `backend/.env`.** It lives in `Phase0/.env` and is read directly by
  `scripts/deploy_agent.py` (or supplied by CI) — the running backend process
  never reads `DEPLOY_BUCKET` or `EXECUTION_ROLE_ARN`.
- **The LLM model provider is env-driven, never hardcoded.** Each agent's
  `model_factory.py` defaults to Amazon Bedrock (SigV4, host credential
  chain) and switches to an enterprise `x-api-key` gateway only when both
  `BEDROCK_ENDPOINT_URL` and `BEDROCK_API_KEY` are set (see
  `Phase0/agents/.env.example` and `cloud_deploy/env/agents.env.example`).
- Never commit AWS credentials or gateway API keys. Keep them in `.env` files
  (gitignored) or the deploy environment, never in code.
