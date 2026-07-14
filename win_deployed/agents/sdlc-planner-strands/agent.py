"""SDLC Planner agent, Strands + AG-UI, served on the AgentCore runtime contract.

Serves POST /invocations (SSE), GET /ping and /ws on port 8080 via the
official bedrock-agentcore AGUIApp helper.
"""

try:
    from dotenv import load_dotenv

    load_dotenv()  # existing env vars win (override=False); .env fills the rest
except ImportError:
    pass

from ag_ui_strands import StrandsAgent
from bedrock_agentcore.runtime.ag_ui import AGUIApp
from strands import Agent

from model_factory import build_strands_model
from tools import show_estimates, show_user_stories

SYSTEM_PROMPT = """You are an SDLC planning assistant for backlog refinement and sprint planning.
For story generation draft 3 to 5 user stories with acceptance criteria and call show_user_stories exactly once with all of them.
For estimation call show_estimates once, covering every current story id.
Never claim tickets were created directly. When asked to create tickets, call request_ticket_approval first, wait for the user decision, then confirm the outcome in text. Ticket creation is simulated in this phase.
Keep chat text short, the cards carry the detail."""


def build_agent() -> StrandsAgent:
    model = build_strands_model()
    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[show_user_stories, show_estimates],
    )
    return StrandsAgent(
        agent=agent,
        name="sdlc-planner",
        description="Backlog refinement and sprint planning assistant",
    )


app = AGUIApp()
app.entrypoint(build_agent())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
