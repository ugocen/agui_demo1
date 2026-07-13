"""Release Readiness agent, LangGraph + AG-UI, served on the AgentCore runtime contract.

Serves POST /invocations (SSE), GET /ping and /ws on port 8080 via the
official bedrock-agentcore AGUIApp helper. The LangGraph and langchain
imports plus graph compilation are deferred to the first invocation so the
container answers /ping well within the runtime initialization window,
instead of blocking module import (which exceeded the 30s init limit).
"""

from bedrock_agentcore.runtime.ag_ui import AGUIApp

app = AGUIApp()

_agui_agent = None


def get_agui_agent():
    global _agui_agent
    if _agui_agent is None:
        from ag_ui_langgraph import LangGraphAgent

        from graph import build_graph

        _agui_agent = LangGraphAgent(
            name="release-readiness",
            description="Pre-deployment release readiness assessment",
            graph=build_graph(),
        )
    return _agui_agent


@app.entrypoint
async def run_agent(run_input):
    request_agent = get_agui_agent().clone()
    async for event in request_agent.run(run_input):
        yield event


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
