"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AgentChat } from "@/components/AgentChat";
import { AuthGate } from "@/components/AuthGate";
import { agentColor, useCatalog, WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { newThreadId } from "@/lib/threads";

function AgentPageInner({ agentId }: { agentId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const catalog = useCatalog();
  // Display name and ui_mode both come from the catalog (synced from AgentCore);
  // no hardcoded per-agent values. The header falls back to the id while it loads.
  const agent = catalog.find((entry) => entry.id === agentId);
  const agentName = agent?.name ?? agentId;
  const [fallbackThread] = useState(() => newThreadId());
  const threadId = searchParams.get("thread");

  useEffect(() => {
    if (!threadId) {
      router.replace(`/agents/${agentId}?thread=${fallbackThread}`);
    }
  }, [threadId, agentId, router, fallbackThread]);

  return (
    <WorkspaceShell>
      <header className="main-header">
        <span className="agent-dot" style={{ background: agentColor(agentId) }}>
          {agentName.slice(0, 1)}
        </span>
        <h1>{agentName}</h1>
        <span className="header-chip">agui</span>
        <span className="header-chip">AgentCore</span>
      </header>
      {/*
        Wait for the catalog entry before mounting the chat: ui_mode decides which
        rendering strategy is wired, so mounting on a guess would start the wrong
        one and then swap catalogs under a live CopilotKitProvider. The backend
        also *is* the AG-UI proxy, so if its catalog is unreachable there is no
        working chat to render anyway.
      */}
      {threadId && agent ? (
        <AgentChat
          agentId={agentId}
          agentName={agentName}
          threadId={threadId}
          uiMode={agent.ui_mode ?? "a2ui"}
        />
      ) : null}
    </WorkspaceShell>
  );
}

export function AgentPage({ agentId }: { agentId: string }) {
  return (
    <AuthGate>
      <Suspense fallback={null}>
        <AgentPageInner agentId={agentId} />
      </Suspense>
    </AuthGate>
  );
}
