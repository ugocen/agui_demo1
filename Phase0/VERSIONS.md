# Pinned Versions, Phase 0

Every dependency pinned at install time is recorded here with the date it was pinned.

| Component | Package | Version | Pinned on |
|---|---|---|---|
| planner agent | strands-agents | 1.47.0 | 2026-07-12 |
| planner agent | ag-ui-strands | 0.2.2 | 2026-07-12 |
| planner agent | bedrock-agentcore | 1.18.0 | 2026-07-12 |
| planner agent | uvicorn | 0.51.0 | 2026-07-12 |
| release agent | langgraph | 1.2.9 | 2026-07-12 |
| release agent | langchain-aws | 1.6.2 | 2026-07-12 |
| release agent | ag-ui-langgraph | 0.0.42 | 2026-07-12 |
| release agent | bedrock-agentcore | 1.18.0 | 2026-07-12 |
| release agent | uvicorn | 0.51.0 | 2026-07-12 |
| bug-report agent | strands-agents | 1.47.0 | 2026-07-12 |
| bug-report agent | ag-ui-strands | 0.2.2 | 2026-07-12 |
| bug-report agent | bedrock-agentcore | 1.18.0 | 2026-07-12 |
| bug-report agent | fastapi | 0.139.0 | 2026-07-12 |
| bug-report agent | uvicorn | 0.51.0 | 2026-07-12 |
| backend | fastapi | 0.139.0 | 2026-07-12 |
| backend | uvicorn | 0.51.0 | 2026-07-12 |
| backend | httpx | 0.28.1 | 2026-07-12 |
| backend | boto3 / botocore[crt] | 1.43.46 | 2026-07-12 |
| backend | PyJWT[crypto] | 2.13.0 | 2026-07-12 |
| backend | python-dotenv | 1.2.2 | 2026-07-12 |
| deploy script | boto3 / botocore[crt] | 1.43.46 | 2026-07-12 |
| smoke tests | httpx | 0.28.1 | 2026-07-12 |
| frontend | next | 16.2.10 | 2026-07-12 |
| frontend | react / react-dom | 19.2.4 | 2026-07-12 |
| frontend | @copilotkit/react-core | 1.62.3 | 2026-07-12 |
| frontend | @copilotkit/runtime | 1.62.3 | 2026-07-12 |
| frontend | @ag-ui/client | 0.0.57 | 2026-07-12 |
| frontend | @azure/msal-browser | 5.17.0 | 2026-07-12 |
| frontend | @azure/msal-react | 5.5.2 | 2026-07-12 |
| frontend | zod | 4.4.3 | 2026-07-12 |
| all 5 agents | boto3 | 1.43.46 | 2026-07-14 |
| all 5 agents | python-dotenv | 1.2.2 | 2026-07-14 |

Note: CopilotKit "current major" on the latest dist-tag is 1.62.x, which ships
the v2 component set under the `@copilotkit/react-core/v2` subpath and the v2
runtime under `@copilotkit/runtime/v2` (2.0.0 itself is still a pre-release on
the `next` tag). The frontend uses the v2 APIs per doc 07 T7.
