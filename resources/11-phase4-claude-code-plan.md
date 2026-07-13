# Phase 4 Implementation Plan for Claude Code, Multi-Agent Experience

Execute after gate G3. Doc 07 section 0 rules apply. Goal: A2A agents live beside AG-UI agents, agent-to-agent flows, per-role controls, ending at gate G4.

## Inputs [Human]

* H1: Empty Bitbucket repo `agp-agent-standup-reporter` (the first A2A agent, SDLC role: daily standup and status summarizer)
* H2: Per-role concurrency and quota numbers to enforce (sessions per user, requests per minute)

## Tasks

### T1, First A2A agent

Steps: create `agp-agent-standup-reporter` from the agent template, Strands or LangGraph (pick the simpler fit), served with the SDK's A2A support (`serve_a2a` executor) instead of AG-UI, deploy through the agent Jenkinsfile with protocol A2A, register with `capability=chat`.
Verify: runtime READY, agent card retrievable, a direct A2A test client completes a task with streaming.
Done when: A2A runtime serving in dev.

### T2, Backend A2A client and generic chat

Steps: implement the backend A2A client (task submit, stream, cancel) mapped to a simple chat SSE API, plus a plain HTTP/SSE fallback path for trivial agents, wire the frontend generic chat screen (already stubbed in Phase 2) to it, persist these threads through the Phase 3 tables.
Verify: the standup agent chats in the generic screen, history persists, cancel works mid-stream.
Done when: catalog shows AG-UI and chat agents side by side, each in its own UI mode.

### T3, Agent-to-agent composite flow

Steps: add a Temporal workflow `sprint_review_pack` that calls the planner agent for backlog summary, the release agent for readiness, and the standup reporter for the narrative, aggregating into one result surfaced in the frontend, agent-to-agent calls go over A2A where an agent consumes another directly.
Verify: one user action produces the composite output, a mid-flow agent failure retries without duplicating side effects.
Done when: composite flow demonstrable and durable.

### T4, Capability metadata and richer rendering

Steps: extend the contracts/agent registry with a `ui_capability` structure (cards supported, shared-state keys, HITL usage), frontend reads it to mount per-agent components dynamically instead of hardcoding, add one agent-specific card variation to prove the path.
Verify: changing capability metadata in the registry changes rendering without a frontend deploy (component must already exist, metadata selects it).
Done when: rendering is registry-driven within the installed card set.

### T5, Quotas and graceful degradation

Steps: enforce H2 numbers via the Phase 3 rate-limit middleware per role, per-user concurrent session cap, handle AgentCore throttling responses with user-visible retry messaging and backoff in the proxy, expose quota metrics to CloudWatch.
Verify: exceeding caps yields clean UX (429 messaging, no broken streams), throttle simulation degrades gracefully.
Done when: limits active and observable.

### T6, G4 regression

Steps: extend the pytest suite: A2A chat round trip, composite workflow success and mid-flow retry, capability-driven mounting, quota enforcement.
Done when: suite green in pipeline, gate G4 checklist posted to Jira [Human].

## Gate G4 mapping

AG-UI and A2A agents side by side in correct modes (T1, T2), composite delegated flow completing (T3).
