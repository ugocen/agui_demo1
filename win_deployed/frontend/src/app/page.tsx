"use client";

import { useRouter } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { AuthGate, useAccessToken } from "@/components/AuthGate";
import {
  agentColor,
  CatalogAgent,
  useCatalog,
  WorkspaceShell,
} from "@/components/workspace/WorkspaceShell";
import { BACKEND_URL } from "@/lib/config";
import { newThreadId } from "@/lib/threads";

type Runtime = {
  name: string;
  id: string;
  arn: string;
  status: string;
  version: string;
  protocol: string;
  registered: boolean;
  last_updated: string | null;
};

function DiscoveredAgents({ agents }: { agents: CatalogAgent[] }) {
  const token = useAccessToken();
  const router = useRouter();
  const [runtimes, setRuntimes] = useState<Runtime[] | null>(null);
  // A scan runs on mount, so start in the loading state.
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // The fetch itself — setState is only reached inside async callbacks, so this
  // is safe to call from an effect without a synchronous setState-in-effect.
  const fetchRuntimes = useCallback(() => {
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
    return fetch(`${BACKEND_URL}/api/agentcore/runtimes`, { headers })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`${response.status} ${await response.text()}`);
        }
        return response.json();
      })
      .then((data: Runtime[]) => {
        setRuntimes(data);
        setError(null);
      })
      .catch((fetchError) => setError(String(fetchError)))
      .finally(() => setLoading(false));
  }, [token]);

  // A manual rescan is a user event, where synchronous loading feedback is fine.
  const scan = () => {
    setLoading(true);
    setError(null);
    fetchRuntimes();
  };

  useEffect(() => {
    fetchRuntimes();
  }, [fetchRuntimes]);

  const catalogForArn = (arn: string): CatalogAgent | undefined =>
    agents.find((agent) => agent.runtime_arn === arn);

  const openChat = (agentId: string) => {
    router.push(`/agents/${agentId}?thread=${newThreadId()}`);
  };

  return (
    <>
      <div className="section-title" style={{ marginTop: 0 }}>
        Agents on AgentCore
        <button className="ghost-btn" onClick={scan} disabled={loading}>
          {loading ? "Scanning…" : "Rescan"}
        </button>
      </div>
      <p className="hero-sub" style={{ marginBottom: 24 }}>
        Live from the AgentCore control plane. Registered runtimes are chat-ready; click one to start
        a session.
      </p>
      {error ? <p style={{ color: "var(--accent)" }}>{error}</p> : null}
      {runtimes === null ? <p style={{ color: "var(--text-muted)" }}>Scanning AgentCore…</p> : null}

      <div className="agent-grid">
        {(runtimes ?? []).map((runtime) => {
          const catalog = catalogForArn(runtime.arn);
          const clickable = Boolean(catalog);
          return (
            <div
              key={runtime.id}
              className={`agent-card ${clickable ? "clickable" : "disabled"}`}
              onClick={() => catalog && openChat(catalog.id)}
              title={clickable ? "Start a chat" : "Deployed but not registered in the platform"}
            >
              <span
                className="agent-dot"
                style={{ background: catalog ? agentColor(catalog.id) : "#9a9aa4" }}
              >
                {(catalog?.name ?? runtime.name).slice(0, 1).toUpperCase()}
              </span>
              <strong>{catalog?.name ?? runtime.name}</strong>
              <p>
                {catalog?.description ?? (
                  <span style={{ color: "var(--text-muted)" }}>
                    Deployed to AgentCore, not registered in the platform catalog.
                  </span>
                )}
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                <span className="badge badge-blue">{runtime.protocol || "?"}</span>
                <span
                  className={`badge ${runtime.status === "READY" ? "badge-green" : "badge-gray"}`}
                >
                  {runtime.status}
                </span>
                <span className="badge badge-gray">v{runtime.version}</span>
                {!catalog ? <span className="badge badge-gray">unregistered</span> : null}
              </div>
            </div>
          );
        })}
      </div>
      {runtimes && runtimes.length === 0 ? (
        <p style={{ color: "var(--text-muted)" }}>No runtimes found in this account/region.</p>
      ) : null}
    </>
  );
}

function HomeInner() {
  const agents = useCatalog();

  return (
    <WorkspaceShell>
      <div className="home-main">
        <div className="home-container">
          <div className="hero-title">Generative UI demo for AI SDLC</div>
          <p className="hero-sub">
            A demo playground for building and testing agents that render Generative UI with
            CopilotKit, AG-UI, and A2UI — part of the AI SDLC Orchestration platform initiative.
          </p>
          <DiscoveredAgents agents={agents} />
        </div>
      </div>
    </WorkspaceShell>
  );
}

export default function Home() {
  return (
    <AuthGate>
      <Suspense fallback={null}>
        <HomeInner />
      </Suspense>
    </AuthGate>
  );
}
