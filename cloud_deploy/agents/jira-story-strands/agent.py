"""Jira Story Writer — Strands + AG-UI, static-card agent with screenshot input.

Turns product input (free text, often dictated and mixed-language, plus optional
screenshots of the current screen and the expected design) into a Jira-ready User
Story with Given-When-Then acceptance criteria, published as raw Jira markup on
the document canvas for copy-paste.

WHY THIS IS ONE AGENT AND NOT A PIPELINE OF THEM
The specification this implements describes a deterministic orchestrator calling
a series of sub-agents. `ag_ui_strands.StrandsAgent` wraps exactly ONE
`strands.Agent` — its constructor takes `(agent, name, description, config,
hooks)` and rebuilds a `strands.Agent` per thread, with no callable or custom
runner to plug an orchestrator into. A hand-written async generator handed to
`AGUIApp.entrypoint()` would be the alternative (the entrypoint is duck-typed),
but it would mean re-implementing AG-UI event translation, the frontend
client-proxy tool bridge and the HITL halt — the exact machinery the adapter
exists to provide.

So the pipeline lives in the PROMPT as an ordered tool sequence, and the parts
that must not vary live in PYTHON:

  * `jira_render.py` owns every character of the markup (section order, keyword
    bolding, the two-space AND/BUT indent, flat AC numbering).
  * `jira_lint.py` decides the format half of the 30-item checklist by reading
    the rendered bytes.

The model supplies content and judgement; it never emits markup and never grades
its own formatting. `publish_jira_story` does both in one call, so a failed check
comes back inside the same turn and the repair loop is a normal tool retry.

SCREENSHOTS
There is no separate vision step. CopilotKit sends an attached image as
multimodal user-message content, `ag_ui_strands` converts it to a Bedrock image
ContentBlock, and the model simply sees it. `show_design_context` is how the
agent REPORTS what it read, not how it reads. Note the adapter's format allow
list is exactly {png, jpeg, gif, webp} and it drops anything else silently — the
frontend normalizes MIME types before upload for that reason.

WHY emit_messages_snapshot IS OFF (this is load-bearing, do not "restore the
default")
ag_ui_strands 0.2.2 builds its MESSAGES_SNAPSHOT with
`UserMessage(content=_coerce_text(msg.content))` (agent.py:148), and
`_coerce_text` falls through to `str(content)` for anything that is not already a
string. A multimodal user message is a LIST of pydantic models, so the snapshot
carries its Python repr:

    "[TextInputContent(type='text', text='here is the screen'),
      ImageInputContent(..., value='iVBORw0KGgoAAA…')]"

— the entire base64 payload, inlined as TEXT. That snapshot is emitted right
after RUN_STARTED, and @ag-ui/client treats it as authoritative: on
MESSAGES_SNAPSHOT it rebuilds its list as
`messages.filter(m => byId.has(m.id)).map(m => byId.get(m.id))`, replacing the
client's copy of the user message with the stringified one. The image survives
the turn it arrives on (`_build_strands_history` converts independently) and is
destroyed for every turn after it — replaced by hundreds of thousands of tokens
of base64 prose that the client then re-sends forever.

Turning the snapshot off costs nothing here. The client's message tree is built
by the streaming events on their own: TOOL_CALL_START creates the assistant
message (`ee()` pushes `{id: toolCallId, role: "assistant", toolCalls: []}` when
no parentMessageId is given), TOOL_CALL_ARGS/END fill it, TOOL_CALL_RESULT
splices the tool message in after its call, and TEXT_MESSAGE_START creates the
text message. Cards, the HITL pause and the transcript all keep working; what
goes away is the adapter overwriting the client's own history with a lossy
reconstruction of it.

This is scoped to this agent — the other five keep the default, since none of
them sends multimodal content.

The two `request_*` tools are frontend-owned (see components/hitl). They are not
defined here on purpose: a backend tool of the same name silently wins the
registry collision and the card would never render.
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
# the zip, so LOCAL_DEV is present locally and absent on AgentCore.
if os.environ.get("LOCAL_DEV", "").strip().lower() in ("1", "true", "yes", "on"):
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from ag_ui_strands import StrandsAgent, StrandsAgentConfig, ToolBehavior
from bedrock_agentcore.runtime.ag_ui import AGUIApp
from strands import Agent

from model_factory import build_strands_model
from prompts import SYSTEM_PROMPT
from tools import ALL_TOOLS, PIPELINE_STEPS, TOOL_STEPS

# Per-thread progress, so the run timeline survives across the turns of one
# conversation. Bounded because a long-lived AgentCore runtime sees every thread
# it has ever served; the entries are two short lists each.
_PIPELINE_BY_THREAD: dict[str, dict] = {}
_MAX_TRACKED_THREADS = 512


def _tracked(input_data) -> dict:
    """Progress for this thread, seeded once from whatever the client echoed back.

    The adapter seeds its `current_state` from `RunAgentInput.state` at run start
    and only ever emits whole-object STATE_SNAPSHOTs (there is no STATE_DELTA in
    ag_ui_strands 0.2.2), so reading the client's echo here is what makes the
    timeline survive a page reload instead of restarting at step one.
    """
    thread_id = str(getattr(input_data, "thread_id", "") or "-")
    tracked = _PIPELINE_BY_THREAD.get(thread_id)
    if tracked is None:
        if len(_PIPELINE_BY_THREAD) >= _MAX_TRACKED_THREADS:
            _PIPELINE_BY_THREAD.pop(next(iter(_PIPELINE_BY_THREAD)), None)
        echoed = (getattr(input_data, "state", None) or {}).get("pipeline") or {}
        done = [step for step in (echoed.get("done") or []) if isinstance(step, str)]
        tracked = {"done": done, "current": ""}
        _PIPELINE_BY_THREAD[thread_id] = tracked
    return tracked


def _snapshot(tracked: dict) -> dict:
    return {
        "pipeline": {
            "steps": PIPELINE_STEPS,
            "done": list(tracked["done"]),
            "current": tracked["current"],
        }
    }


def _on_tool_call(context) -> dict | None:
    """Mark the step this tool call starts as running."""
    step = TOOL_STEPS.get(context.tool_name)
    if step is None:
        return None
    tracked = _tracked(context.input_data)
    tracked["current"] = step
    return _snapshot(tracked)


def _on_tool_result(context) -> dict | None:
    """Mark it finished. Without this the last step would render as stuck."""
    step = TOOL_STEPS.get(context.tool_name)
    if step is None:
        return None
    tracked = _tracked(context.input_data)
    if step not in tracked["done"]:
        tracked["done"].append(step)
    tracked["current"] = ""
    return _snapshot(tracked)


def build_agent() -> StrandsAgent:
    model = build_strands_model()
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=ALL_TOOLS)
    # state_from_args/state_from_result are the only state hooks that also update
    # the adapter's `current_state`. A tool that merely YIELDS {"state": ...} does
    # emit a live snapshot, but the terminal StateSnapshotEvent at end of run is
    # built from `current_state` alone and would wipe it — so the timeline has to
    # go through these two.
    config = StrandsAgentConfig(
        # See the module docstring: leaving this on stringifies every uploaded
        # screenshot into the client's history as base64 prose.
        emit_messages_snapshot=False,
        tool_behaviors={
            name: ToolBehavior(state_from_args=_on_tool_call, state_from_result=_on_tool_result)
            for name in TOOL_STEPS
        },
    )
    return StrandsAgent(
        agent=agent,
        name="jira-story",
        description="Writes Jira user stories with Given-When-Then acceptance criteria from text and screenshots",
        config=config,
    )


app = AGUIApp()
app.entrypoint(build_agent())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
