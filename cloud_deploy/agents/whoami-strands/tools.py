"""The three things this agent can do, as Strands tools.

Each one is a thin wrapper over `identity.py` — the split is not ceremony: the
tool docstrings are what the model reads to choose between them, so they are
written for the model, while the auth reasoning lives next to the code that does
it. Every tool returns a plain dict; nothing here raises, because "I could not
reach Graph" and "no token arrived" are answers the user asked for, not failures
to hide behind a tool error.

No tool ever returns a token. The identity module hands back a 12-hex
fingerprint instead, which is enough to tell two runs apart and useless to
anyone who reads a transcript.
"""

from opentelemetry import trace
from strands import tool

from identity import resolve_identity, runtime_auth_facts

tracer = trace.get_tracer("whoami-strands")


@tool
def whoami() -> dict:
    """Identify the signed-in user from the access token that reached this agent.

    Returns the identity claims (name, username/email, directory object id,
    tenant, any roles or groups the tenant emits), how the token arrived, and
    whether its signature could be verified. Fast — reads the token only, makes
    no directory call. Use this for "who am I", "which account am I signed in
    as", "what does my token say".
    """
    with tracer.start_as_current_span("tool.whoami"):
        return resolve_identity(with_profile=False)


@tool
def my_profile() -> dict:
    """Look up the caller's full person record in the company directory.

    Adds what the token cannot carry — job title, department, office, phone,
    display name as the directory holds it — by calling Microsoft Graph /me with
    a token obtained on the caller's behalf (AgentCore Identity OBO exchange, or
    the token relayed by the platform). Use this for "what is my job title",
    "which department am I in", "show my profile", or any question about the
    person rather than the session.

    When no Graph token can be obtained the identity claims are still returned,
    with a note explaining which piece of configuration is missing — say so
    plainly rather than implying the directory has no answer.
    """
    with tracer.start_as_current_span("tool.my_profile"):
        return resolve_identity(with_profile=True)


@tool
def auth_diagnostics() -> dict:
    """Explain the authentication path this request actually travelled.

    Reports which headers reached the runtime (names only, never values), whether
    the token came through AgentCore's JWT authorizer or was relayed by the
    backend proxy, what this runtime pins (tenant, audience), whether an OBO
    credential provider is configured, and the OpenTelemetry trace id for this
    run. Use it for "why can't you see my profile", "is JWT auth working", "is
    OBO configured", or when an answer above was degraded and the user asks why.
    """
    with tracer.start_as_current_span("tool.auth_diagnostics"):
        identity = resolve_identity(with_profile=False)
        return {
            "runtime": runtime_auth_facts(),
            "token_source": identity["token_source"],
            "token_fingerprint": identity["token_fingerprint"],
            "verification": identity["verification"],
            "token": identity.get("token", {}),
            "notes": identity["notes"],
        }


ALL_TOOLS = [whoami, my_profile, auth_diagnostics]
