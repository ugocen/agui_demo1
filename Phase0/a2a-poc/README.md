# A2A proof of concept (Phase 0)

A minimal, **fully local** Agent-to-Agent (A2A) demo — no AWS, no Bedrock. It
proves the two halves of the A2A protocol end to end and is shaped exactly like
an Amazon Bedrock AgentCore A2A runtime, so it can graduate to the cloud later
without protocol changes.

This is **separate** from the AG-UI chat app and does not touch it. AG-UI is
agent↔UI (what the CopilotKit frontend renders); A2A is agent↔agent (JSON-RPC).

## What it shows

- **Discovery** — `GET /.well-known/agent-card.json` returns an *Agent Card*
  (name, version, capabilities, skills) — how another agent finds and understands
  this one.
- **Invocation** — `POST /` handles JSON-RPC 2.0 `message/send` and returns the
  agent's reply message.
- **Health** — `GET /ping`.

The skill (`plan`) is deterministic demo logic so it runs with no model access.

## Run it

```bash
# from Phase0/a2a-poc/  (reuse the backend venv, or: pip install -r requirements.txt)
../backend/.venv/bin/python server.py          # A2A server on :9000
# in another terminal:
../backend/.venv/bin/python client.py "add Microsoft SSO login"
```

Expected: the client prints the discovered Agent Card, then the agent's plan.

Peek at the raw protocol:

```bash
curl -s localhost:9000/.well-known/agent-card.json | jq
curl -s localhost:9000/ -H 'content-type: application/json' -d '{
  "jsonrpc":"2.0","id":"1","method":"message/send",
  "params":{"message":{"role":"user","kind":"message","messageId":"m1",
    "parts":[{"kind":"text","text":"add SSO login"}]}}}' | jq
```

## Why it matches AgentCore's A2A contract

AgentCore's A2A runtime expects: host `0.0.0.0`, **port 9000**, root path `/`,
health `/ping`, Agent Card at `/.well-known/agent-card.json`, JSON-RPC — which is
exactly what this server does. AgentCore adds SigV4 / OAuth 2.0 (our Entra JWT
authorizer fits) and session isolation on top, passing JSON-RPC through unchanged.

## Graduating this POC (next steps, not done here)

1. **Containerise** (ARM64) and deploy as an AgentCore runtime with
   `serverProtocol: "A2A"` (vs the current agents' `"AGUI"`).
2. **Auth**: attach the OAuth/JWT inbound authorizer (same Entra app as the SSO)
   so callers present a bearer token.
3. **Make it real**: replace `_demo_plan()` with a call to the actual Strands/
   LangGraph agent (reuse the AG-UI proxy or the agent SDK).
4. **Wire into the platform**: register A2A agents in the catalog (the schema
   already reserves `protocol[agui|a2a|http]`) and/or put an *orchestrator* agent
   in front so the AG-UI chat can drive A2A agents behind the scenes.
