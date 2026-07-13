# Bedrock, Anthropic use case details form

The form that appears in the AWS console the first time you request access to
Anthropic (Claude) models in a region: Bedrock → Model access → Modify model
access → (Anthropic) → "Submit use case details". Fill it once per account.

Fields marked [YOURS] must be your real values, the rest can be pasted as-is.

Personal AWS account, individual use.

| Form field | What to enter |
|---|---|
| Company name | [YOURS] your name |
| Company website URL | [YOURS] personal site or GitHub URL (or leave blank if optional) |
| Industry | Technology / Software |
| Intended users | Just myself |
| Are you using AWS on behalf of a company or yourself? | Yourself |
| Country / region | [YOURS] |
| Use case description | Paste the block below |
| Will outputs be used to make automated decisions about individuals? | No |
| Is this for a regulated / high-risk domain (legal, medical, financial advice)? | No |

## Use case description (paste as-is)

```
I am building a personal project to learn Amazon Bedrock AgentCore and the AG-UI protocol. AI agents run on AgentCore Runtime and are used through a small web app I run locally. Claude models power software-development-lifecycle assistant agents that draft user stories and story-point estimates, and produce release checklists, risk matrices, and go/no-go recommendations, rendered as generative UI cards. A human always makes the final decision.

I call Claude through the Bedrock Converse API for text generation and tool calling. This is a personal, non-commercial project, not customer-facing, and is not used for automated decisions about individuals or for any regulated, legal, medical, or financial-advice use case.
```

## Notes

- Approval is usually granted within a few minutes for Claude models.
- If you also plan to try Sonnet later, tick both Haiku 4.5 and Sonnet 4.5 in the
  same request so their access is ready when you switch `BEDROCK_MODEL_ID`.
- Access is per-region. Request it in the same region as `AWS_REGION` in `.env`
  (currently `us-east-1`). If you later deploy in another region, request there too.
