"""Whoami — Strands + AG-UI, the identity agent. JWT inbound auth, OBO, OTel.

The other five agents never learn who is talking to them: the backend proxy
SigV4-signs every AgentCore call as the trusted caller, and the user's Entra
identity stops at the platform boundary. This one is the counter-example — it
answers "who am I?" from the caller's own token, and explains the path that token
took to get here.

THE ENTRYPOINT TAKES A `context`, AND THE PARAMETER NAME IS LOAD-BEARING
`StrandsAgent.run(self, input_data)` takes exactly one argument, and `AGUIApp`
decides whether to pass the request context by INSPECTING THE HANDLER SIGNATURE:
`_takes_context` returns true only when the second parameter is literally named
`context` (bedrock_agentcore/runtime/ag_ui.py). So an agent that needs request
headers cannot hand `StrandsAgent` straight to `entrypoint()` the way the other
agents do — it has to be wrapped by a function with that exact shape. Renaming
the parameter would not fail loudly; it would silently stop passing headers, and
the agent would report every caller as anonymous.

WHY THERE IS NO SPAN AROUND THE STREAM
The obvious `with tracer.start_as_current_span(...)` around the `async for` below
is exactly the pattern that breaks here: attaching a span context and detaching
it across an async-generator yield is what makes Strands' own OTel
instrumentation crash the local SSE stream (see the LOCAL_DEV note below). The
spans in this agent are therefore all short-lived and synchronous — one per tool
call, inside the tool — which is both safe and the level a reader of a trace
actually wants. The ASGI span for POST /invocations comes from ADOT for free.

Locally: `python agent.py` serves /invocations + /ping on :8080. Nothing
validates a token there, so pass one yourself:
    curl -s localhost:8080/invocations -H 'Authorization: Bearer <entra-token>' \\
      -H 'Content-Type: application/json' -d '{"threadId":"t","runId":"r",
      "messages":[{"id":"m","role":"user","content":"who am I?"}],"tools":[],
      "context":[],"state":{},"forwardedProps":{}}'
"""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()  # existing env vars win (override=False); .env fills the rest
except ImportError:
    pass

# Strands' OpenTelemetry span instrumentation crashes the local SSE stream
# (contextvar detach across the async-generator boundary), so a local run has to
# turn OTEL off. Keyed off an explicit LOCAL_DEV flag (set it in agents/.env) —
# inferring "am I local?" from an injected variable was wrong once already and
# silently disabled the tracing we deploy AgentCore to get. .env never ships in
# the zip, so LOCAL_DEV is present locally and absent on AgentCore. That tracing
# comes from ADOT and only ADOT: aws-opentelemetry-distro in requirements.txt
# plus the ["opentelemetry-instrument", "agent.py"] entry point in
# deploy_agent.py — runtime hosting alone emits stdout logs and nothing else.
if os.environ.get("LOCAL_DEV", "").strip().lower() in ("1", "true", "yes", "on"):
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from ag_ui_strands import StrandsAgent
from bedrock_agentcore.runtime.ag_ui import AGUIApp
from strands import Agent

from identity import remember_request_headers
from model_factory import build_strands_model
from prompts import SYSTEM_PROMPT
from tools import ALL_TOOLS


def build_agent() -> StrandsAgent:
    model = build_strands_model()
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=ALL_TOOLS)
    return StrandsAgent(
        agent=agent,
        name="whoami",
        description="Identifies the signed-in user from their Entra token and looks up their directory profile",
    )


_agent = build_agent()


async def entrypoint(input_data, context):
    """AG-UI handler. The second parameter MUST be named `context` — see above.

    All it adds to `StrandsAgent.run` is one line: record this request's headers
    so the tools can find the caller's token. Everything else about the run —
    event translation, tool dispatch, the SSE stream — stays with the adapter.
    """
    remember_request_headers(getattr(context, "request_headers", None))
    async for event in _agent.run(input_data):
        yield event


app = AGUIApp()
app.entrypoint(entrypoint)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
