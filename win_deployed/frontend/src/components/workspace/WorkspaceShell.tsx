"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { useAccessToken, useMe } from "@/components/AuthGate";
import { BACKEND_URL } from "@/lib/config";
import { listThreads, ThreadRecord } from "@/lib/threads";

export type CatalogAgent = {
  id: string;
  name: string;
  description: string;
  capability: string;
  runtime_arn?: string;
};

// A stable, distinct color per agent derived from its id — no hardcoded
// per-agent list, so any newly synced agent gets its own color for free.
export function agentColor(agentId: string): string {
  let hash = 0;
  for (let i = 0; i < agentId.length; i += 1) {
    hash = (hash * 31 + agentId.charCodeAt(i)) | 0;
  }
  return `hsl(${Math.abs(hash) % 360} 45% 55%)`;
}

export function useCatalog(): CatalogAgent[] {
  const token = useAccessToken();
  const [agents, setAgents] = useState<CatalogAgent[]>([]);

  useEffect(() => {
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
    fetch(`${BACKEND_URL}/api/agents`, { headers })
      .then((response) => (response.ok ? response.json() : []))
      .then(setAgents)
      .catch(() => setAgents([]));
  }, [token]);

  return agents;
}

// Threads live in localStorage (see lib/threads) and change via a custom
// "phase0-threads-changed" event. Subscribe the React-recommended way with
// useSyncExternalStore — no setState inside an effect. The snapshot is cached
// and only invalidated when the event fires, so getSnapshot returns a stable
// reference between changes (required to avoid an infinite render loop). The
// server snapshot is empty, which matches SSR and avoids a hydration mismatch.
const NO_THREADS: ThreadRecord[] = [];
let threadsCache: ThreadRecord[] | null = null;

function getThreadsSnapshot(): ThreadRecord[] {
  if (threadsCache === null) {
    threadsCache = listThreads();
  }
  return threadsCache;
}

function subscribeThreads(onChange: () => void): () => void {
  const handler = () => {
    threadsCache = null;
    onChange();
  };
  window.addEventListener("phase0-threads-changed", handler);
  return () => window.removeEventListener("phase0-threads-changed", handler);
}

function useThreads(): ThreadRecord[] {
  return useSyncExternalStore(subscribeThreads, getThreadsSnapshot, () => NO_THREADS);
}

function timeLabel(timestamp: number): string {
  const date = new Date(timestamp);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const agents = useCatalog();
  const me = useMe();
  const threads = useThreads();

  const activeAgentId = pathname.startsWith("/agents/") ? pathname.split("/")[2] : null;
  const activeThreadId = searchParams.get("thread");

  return (
    <div className="workspace">
      <aside className="sidebar">
        <Link href="/" className="sidebar-brand">
          <span className="brand-mark">P0</span>
          <span>Agent Platform</span>
        </Link>

        <Link href="/" className="new-chat-btn">
          <span style={{ fontSize: 16, lineHeight: 1 }}>+</span> New chat
        </Link>

        <div className="sidebar-section">
          <div className="sidebar-label">Available agents &amp; tools</div>
          {agents.map((agent) => (
            <Link
              key={agent.id}
              href={`/agents/${agent.id}`}
              className={`sidebar-item ${activeAgentId === agent.id ? "active" : ""}`}
            >
              <span className="agent-dot" style={{ background: agentColor(agent.id) }}>
                {agent.name.slice(0, 1)}
              </span>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {agent.name}
              </span>
            </Link>
          ))}
          {agents.length === 0 ? (
            <div className="sidebar-label" style={{ color: "var(--text-muted)" }}>
              Backend unreachable
            </div>
          ) : null}
        </div>

        <div className="sidebar-section sidebar-history">
          <div className="sidebar-label">History</div>
          {threads.slice(0, 20).map((thread) => (
            <Link
              key={thread.id}
              href={`/agents/${thread.agentId}?thread=${thread.id}`}
              className={`history-item ${activeThreadId === thread.id ? "active" : ""}`}
            >
              {thread.title}
              <span className="history-time">
                {thread.agentName} · {timeLabel(thread.createdAt)}
              </span>
            </Link>
          ))}
          {threads.length === 0 ? (
            <div className="history-item" style={{ cursor: "default" }}>
              No conversations yet
            </div>
          ) : null}
        </div>

        <div className="sidebar-section" style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}>
          <Link href="/" className={`sidebar-item ${pathname === "/" ? "active" : ""}`}>
            <span className="agent-dot" style={{ background: "#63636e" }}>⌂</span>
            Agent catalog
          </Link>
          {me.mode !== "entra" || me.roles.includes("admin") ? (
            <Link href="/admin" className={`sidebar-item ${pathname.startsWith("/admin") ? "active" : ""}`}>
              <span className="agent-dot" style={{ background: "#63636e" }}>⚙</span>
              Admin
            </Link>
          ) : null}
        </div>

        <div
          className="sidebar-section"
          style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}
        >
          <div className="sidebar-label">Signed in</div>
          <div style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {me.user ?? me.email ?? (me.mode === "iam" ? "Local dev (SSO off)" : "…")}
          </div>
          <div className="sidebar-label" style={{ color: "var(--text-muted)", marginTop: 2 }}>
            {me.mode === "iam"
              ? "AUTH_MODE=iam"
              : me.roles.length > 0
                ? `Roles: ${me.roles.join(", ")}`
                : "No platform role"}
          </div>
        </div>
      </aside>

      <div className="main-pane">{children}</div>
    </div>
  );
}
