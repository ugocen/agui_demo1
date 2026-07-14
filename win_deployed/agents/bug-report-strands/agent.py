"""Bug Report Assistant agent, Strands + AG-UI, served on the AgentCore runtime contract.

A form-wizard agent. The user describes a problem in chat, the agent analyses
it and proposes a structured bug report by calling the draft_bug_report tool
with filled-in field values. The frontend renders an editable form (the card),
the user edits and submits it, and the agent confirms the final report.

draft_bug_report is a human-in-the-loop tool owned by the frontend: CopilotKit
sends its definition in RunAgentInput.tools, ag-ui-strands registers it as a
client proxy tool, and the run pauses until the browser returns the submitted
form. There are no backend-side tools for this agent.
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

SYSTEM_PROMPT = """You are a bug report assistant that turns a user's description into a well-structured bug report.
When the user describes a problem, analyse it and call draft_bug_report exactly once with sensible proposed values for every field: title, severity (one of critical, high, medium, low), steps_to_reproduce, expected_behavior, actual_behavior, environment.
Infer reasonable values from what the user said, keep each field concise and specific.
The user then reviews and edits the form and submits it. After they submit, confirm the final bug report in a short text summary.
Never claim a bug was filed without calling draft_bug_report first and waiting for the submission. Bug filing itself is simulated in this phase.
Keep chat text short, the form carries the detail."""


def build_agent() -> StrandsAgent:
    model = build_strands_model()
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[])
    return StrandsAgent(
        agent=agent,
        name="bug-report",
        description="Structured bug report assistant",
    )


app = AGUIApp()
app.entrypoint(build_agent())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
