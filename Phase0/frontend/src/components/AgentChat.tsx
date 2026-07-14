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
import { HumanInTheLoop } from "@/components/hitl/HumanInTheLoop";

// Generic chat surface for ANY agent. There are no per-agent, hand-authored
// cards and no id/ui_mode special-casing — every agent renders generatively via
// A2UI. Any agent deployed to AgentCore (and synced into the DB catalog) works
// here with zero frontend changes.

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
}: {
  agentId: string;
  agentName: string;
  threadId: string;
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

  return (
    <CopilotKitProvider
      runtimeUrl="/api/copilotkit"
      headers={headers}
      // Every agent renders via A2UI: mount the rich catalog (basic + Mermaid/
      // Chart/Markdown/Html) and send its component schema to the agent so the
      // LLM knows which components it can emit.
      a2ui={{ catalog: richCatalog, includeSchema: true }}
    >
      <FallbackRender />
      <HumanInTheLoop />
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
        {inspectorOpen ? <EventInspector agentId={agentId} /> : null}
      </div>
    </CopilotKitProvider>
  );
}
