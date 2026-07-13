"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AgentChat } from "@/components/AgentChat";
import { AuthGate } from "@/components/AuthGate";
import { agentColor, useCatalog, WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { newThreadId } from "@/lib/threads";

function AgentPageInner({ agentId, agentName }: { agentId: string; agentName: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const catalog = useCatalog();
  const uiMode = catalog.find((agent) => agent.id === agentId)?.ui_mode ?? "static";
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
        <span className="header-chip">{uiMode === "a2ui" ? "A2UI" : "cards"}</span>
        <span className="header-chip">AgentCore</span>
      </header>
      {threadId ? (
        <AgentChat agentId={agentId} agentName={agentName} threadId={threadId} uiMode={uiMode} />
      ) : null}
    </WorkspaceShell>
  );
}

export function AgentPage({ agentId, agentName }: { agentId: string; agentName: string }) {
  return (
    <AuthGate>
      <Suspense fallback={null}>
        <AgentPageInner agentId={agentId} agentName={agentName} />
      </Suspense>
    </AuthGate>
  );
}
