"use client";

import {
  CopilotChat,
  CopilotKitProvider,
  useAgent,
  UseAgentUpdate,
  useDefaultRenderTool,
} from "@copilotkit/react-core/v2";
import "@copilotkit/react-core/v2/styles.css";
import { useEffect, useState } from "react";

import { updateThreadTitle, upsertThread } from "@/lib/threads";
import { useAccessToken } from "@/components/AuthGate";
import { richCatalog } from "@/components/a2ui/richCatalog";
import { DocumentCanvasPanel, DocumentCanvasProvider } from "@/components/canvas/DocumentCanvas";
import { CardCatalog } from "@/components/cards/cardCatalog";
import { HumanInTheLoop } from "@/components/hitl/HumanInTheLoop";
import type { UiMode } from "@/components/workspace/WorkspaceShell";

// Generic chat surface for ANY agent. Nothing here branches on an agent id: the
// only branch is the catalog's `ui_mode`, which picks a rendering STRATEGY, and
// each strategy is a tool-name-keyed catalog that any agent can use. An agent
// deployed to AgentCore (and synced into the DB catalog) works here with zero
// frontend changes.
//
// The two modes are deliberately exclusive, because offering both at once leaves
// the model to guess: an agent told "you have show_user_stories" AND "you may
// compose A2UI" picks between them nondeterministically.
//
//   static — cards only. The A2UI catalog is not mounted and, more importantly,
//            api/copilotkit/route.ts leaves this agent out of the runtime's a2ui
//            list so the LLM is never given the render_a2ui tool at all.
//   a2ui   — A2UI only. richCatalog is mounted and `includeSchema` sends its
//            component schemas to the LLM; no cards are registered.
//
// HITL is mounted in BOTH: those tools are frontend-owned, the run PAUSES on them,
// and agents like bug-report ship `tools=[]` and cannot function without them. They
// are a protocol contract, not a rendering style.

// Any tool an agent calls that the A2UI renderer doesn't already handle shows as
// a small status line, so nothing silently disappears.
function FallbackRender() {
  useDefaultRenderTool(
    {
      render: ({ name, status }) => (
        <div style={{ padding: 6, color: "#888", fontSize: 13 }}>
          {status === "complete" ? "✓" : "⏳"} tool: {name}
        </div>
      ),
    },
    []
  );
  return null;
}

function EventInspector({ agentId }: { agentId: string }) {
  useAgent({
    agentId,
    updates: [UseAgentUpdate.OnStateChanged, UseAgentUpdate.OnMessagesChanged],
  });
  const { agent } = useAgent({ agentId });
  const state = agent?.state ?? {};
  const messages = (agent?.messages ?? []) as { role?: string }[];
  const isRunning = Boolean(agent?.isRunning);

  const roleCounts = messages.reduce<Record<string, number>>((acc, message) => {
    const role = message.role ?? "unknown";
    acc[role] = (acc[role] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <aside className="inspector">
      <div className="inspector-title">
        AG-UI live state
        <span className={`inspector-run ${isRunning ? "on" : ""}`}>
          {isRunning ? "running" : "idle"}
        </span>
      </div>
      <div className="inspector-label">messages</div>
      <div className="inspector-counts">
        {Object.entries(roleCounts).map(([role, count]) => (
          <span key={role} className="badge badge-gray">
            {role}: {count}
          </span>
        ))}
        {messages.length === 0 ? <span className="inspector-empty">none yet</span> : null}
      </div>
      <div className="inspector-label">shared state</div>
      <pre className="inspector-json">
        {Object.keys(state).length ? JSON.stringify(state, null, 2) : "{}"}
      </pre>
    </aside>
  );
}

function ThreadTitleTracker({ agentId, threadId }: { agentId: string; threadId: string }) {
  useAgent({ agentId, updates: [UseAgentUpdate.OnMessagesChanged] });
  const { agent } = useAgent({ agentId });
  useEffect(() => {
    const messages = (agent?.messages ?? []) as { role?: string; content?: unknown }[];
    const firstUser = messages.find((message) => message.role === "user");
    if (firstUser && typeof firstUser.content === "string") {
      updateThreadTitle(threadId, firstUser.content);
    }
  });
  return null;
}

export function AgentChat({
  agentId,
  agentName,
  threadId,
  uiMode,
}: {
  agentId: string;
  agentName: string;
  threadId: string;
  uiMode: UiMode;
}) {
  const token = useAccessToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

  useEffect(() => {
    upsertThread({
      id: threadId,
      agentId,
      agentName,
      title: agentName,
      createdAt: Date.now(),
    });
  }, [threadId, agentId, agentName]);

  const [inspectorOpen, setInspectorOpen] = useState(false);
  const isA2ui = uiMode !== "static";

  return (
    <CopilotKitProvider
      runtimeUrl="/api/copilotkit"
      headers={headers}
      // a2ui mode: mount the rich catalog (basic + Mermaid/Chart/Markdown/Html)
      // and send its component schemas to the agent so the LLM knows what it can
      // emit. static mode passes nothing, so the A2UI renderer stays out.
      a2ui={isA2ui ? { catalog: richCatalog, includeSchema: true } : undefined}
    >
      {/* The canvas is fed by the HITL draft forms and rendered beside the chat,
          so both live under one provider. It opens by itself when a draft
          arrives — there is no per-agent condition on mounting it. */}
      <DocumentCanvasProvider>
        <FallbackRender />
        {isA2ui ? null : <CardCatalog />}
        <HumanInTheLoop agentId={agentId} />
        <ThreadTitleTracker agentId={agentId} threadId={threadId} />
        <div className="chat-body">
          <div className="chat-region">
            <div className="chat-toolbar">
              <span />
              <button
                className="ghost-btn"
                onClick={() => setInspectorOpen((open) => !open)}
                title="Inspect the live AG-UI state and message stream"
              >
                {inspectorOpen ? "Hide inspector" : "Inspect state"}
              </button>
            </div>
            <div className="chat-host">
              <CopilotChat key={threadId} agentId={agentId} threadId={threadId} />
            </div>
          </div>
          <DocumentCanvasPanel />
          {inspectorOpen ? <EventInspector agentId={agentId} /> : null}
        </div>
      </DocumentCanvasProvider>
    </CopilotKitProvider>
  );
}
