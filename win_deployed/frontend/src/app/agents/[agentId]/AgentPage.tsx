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
  // Display name comes from the catalog (synced from AgentCore); fall back to the
  // id until the catalog loads. No hardcoded per-agent names.
  const agentName = catalog.find((agent) => agent.id === agentId)?.name ?? agentId;
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
      {threadId ? (
        <AgentChat agentId={agentId} agentName={agentName} threadId={threadId} />
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
