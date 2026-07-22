"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { AgentChat } from "@/components/AgentChat";
import { AuthGate, useAccessToken } from "@/components/AuthGate";
import { agentColor, useCatalog, WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { BACKEND_URL } from "@/lib/config";
import { newThreadId } from "@/lib/threads";

type Health = { alive: boolean; detail: string };

// Before the agent is usable, prove its runtime is actually up. The control
// plane reports READY even when a container can't boot, so this hits the
// backend's liveness endpoint, which opens a real AG-UI run and waits for
// RUN_STARTED. Non-blocking: the chat mounts immediately; this banner resolves
// on its own a few seconds later.
function AgentHealthBanner({ agentId, agentName }: { agentId: string; agentName: string }) {
  const token = useAccessToken();
  const [health, setHealth] = useState<Health | null>(null);
  // A probe runs on mount, so start in the checking state. setState below is only
  // reached inside async callbacks, so runProbe is safe to call from an effect.
  const [checking, setChecking] = useState(true);

  const runProbe = useCallback(() => {
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
    return fetch(`${BACKEND_URL}/api/agui/${agentId}/health`, { headers })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`${response.status} ${await response.text()}`);
        }
        return response.json();
      })
      .then((data: Health) => setHealth(data))
      .catch((error) => setHealth({ alive: false, detail: String(error) }))
      .finally(() => setChecking(false));
  }, [agentId, token]);

  // A manual retry is a user event, where synchronous feedback is fine.
  const retry = () => {
    setChecking(true);
    setHealth(null);
    runProbe();
  };

  useEffect(() => {
    runProbe();
  }, [runProbe]);

  if (checking) {
    return (
      <div className="health-banner checking">
        <span className="health-dot" />
        Checking whether {agentName} is up…
      </div>
    );
  }
  if (health?.alive) {
    return (
      <div className="health-banner ok">
        <span className="health-dot" />
        {agentName} is up and running — send a message to start using it.
      </div>
    );
  }
  return (
    <div className="health-banner bad">
      <span className="health-dot" />
      <span>
        {agentName} isn’t responding{health?.detail ? `: ${health.detail}` : "."}
      </span>
      <button className="health-retry" onClick={retry}>
        Retry
      </button>
    </div>
  );
}

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
      {agent ? <AgentHealthBanner agentId={agentId} agentName={agentName} /> : null}
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
          acceptsFiles={agent.accepts_files ?? false}
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
