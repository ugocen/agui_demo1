---
description: One-time AWS bootstrap — IAM setup for Phase 0
---

Set up the AWS IAM prerequisites for Phase 0:

1. Confirm the `aws` CLI is configured under a **dedicated IAM deployment
   user**, never root: `aws sts get-caller-identity`.
2. Attach `Phase0/aws-setup/deploy-user-policy.json` to that user (AgentCore,
   Bedrock invoke, S3 on `agui-demo1-deploy-122524101917`, `iam:PassRole` on
   `agui-demo1-runtime-exec`, CloudWatch Logs read).
3. Create the `agui-demo1-runtime-exec` role with
   `Phase0/aws-setup/execution-role-trust.json` and attach
   `Phase0/aws-setup/execution-role-policy.json`. Traces additionally need
   CloudWatch Transaction Search enabled once per account+region.
4. Fill `AWS_REGION`, `DEPLOY_BUCKET`, `EXECUTION_ROLE_ARN`, and
   `BEDROCK_MODEL_ID` in `Phase0/.env`.

Never commit AWS credentials. See `.agents/rules/40-aws.md` for the account,
region, bucket, and role facts.
