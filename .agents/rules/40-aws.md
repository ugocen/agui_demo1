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
- **The LLM provider is forked, not configured** (invariant 4). There is no
  runtime switch: `Phase0/agents/<a>/model_factory.py` is Amazon Bedrock only
  (SigV4, host credential chain) and has no gateway code path;
  `cloud_deploy/agents/<a>/model_factory.py` is gateway only (`x-api-key`) and has
  no Bedrock code path, requires `BEDROCK_ENDPOINT_URL` + `BEDROCK_API_KEY` +
  `BEDROCK_MODEL_ID`, and raises without them. See `Phase0/agents/.env.example`
  and `cloud_deploy/env/agents.env.example`. Never hardcode a model id.
- Never commit AWS credentials or gateway API keys. Keep them in `.env` files
  (gitignored) or the deploy environment, never in code.
