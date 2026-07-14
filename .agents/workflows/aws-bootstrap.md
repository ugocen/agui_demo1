---
description: One-time AWS bootstrap — IAM setup for Phase 0
---

## Steps

### 1. Preconditions
- The `aws` CLI is installed and credentials are configured. Confirm with
  `aws sts get-caller-identity`.
- IMPORTANT: local AWS credentials should resolve to a **dedicated IAM
  deployment user**, never the root account. Create that user first if it
  does not exist yet.

### 2. Deployer permissions
- Attach `Phase0/aws-setup/deploy-user-policy.json` to the deployment user. It
  scopes AgentCore (`bedrock-agentcore:*`), Bedrock invoke/converse, S3 on the
  deploy bucket (`agui-demo1-deploy-122524101917`), `iam:PassRole` on the
  execution role (`agui-demo1-runtime-exec`), and CloudWatch Logs read.

### 3. Runtime execution role
- Create `agui-demo1-runtime-exec` with the trust policy in
  `Phase0/aws-setup/execution-role-trust.json` (trusts
  `bedrock-agentcore.amazonaws.com`) and attach
  `Phase0/aws-setup/execution-role-policy.json` (Bedrock invoke/converse,
  CloudWatch Logs, X-Ray).

### 4. Verify
- `aws sts get-caller-identity` under the deployment user's credentials.
- Fill `AWS_REGION`, `DEPLOY_BUCKET=agui-demo1-deploy-122524101917`,
  `EXECUTION_ROLE_ARN=arn:aws:iam::122524101917:role/agui-demo1-runtime-exec`,
  and `BEDROCK_MODEL_ID` in `Phase0/.env`.

Never commit AWS credentials. See `.agents/rules/40-aws.md` for the account,
region, bucket, and role facts.
