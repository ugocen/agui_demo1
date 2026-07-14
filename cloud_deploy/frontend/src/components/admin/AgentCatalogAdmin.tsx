"use client";

import { useCallback, useEffect, useState } from "react";

import { useAccessToken } from "@/components/AuthGate";
import { agentColor } from "@/components/workspace/WorkspaceShell";
import { BACKEND_URL } from "@/lib/config";

type CatalogEntry = {
  agent_id: string;
  display_name: string;
  description: string;
  enabled: boolean;
  required_role: string;
  // AgentCore-sourced, read-only
  runtime_arn: string;
  runtime_name: string;
  protocol: string;
  status: string;
  version: string;
  last_synced_at: string | null;
};

type Editable = Pick<
  CatalogEntry,
  "display_name" | "description" | "enabled" | "required_role"
>;

const EDITABLE_KEYS = [
  "display_name",
  "description",
  "enabled",
  "required_role",
] as const;

export function AgentCatalogAdmin() {
  const token = useAccessToken();
  const [entries, setEntries] = useState<CatalogEntry[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Partial<Editable>>>({});
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);

  const authHeaders = useCallback((): Record<string, string> => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
  }, [token]);

  const load = useCallback(() => {
    setError(null);
    fetch(`${BACKEND_URL}/api/admin/catalog`, { headers: authHeaders() })
      .then(async (response) => {
        if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
        return response.json();
      })
      .then(setEntries)
      .catch((fetchError) => setError(String(fetchError)));
  }, [authHeaders]);

  useEffect(() => {
    load();
  }, [load]);

  const sync = () => {
    setSyncing(true);
    setSyncMsg(null);
    setError(null);
    fetch(`${BACKEND_URL}/api/admin/catalog/sync`, { method: "POST", headers: authHeaders() })
      .then(async (response) => {
        if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
        return response.json();
      })
      .then((data: { result: { added: string[]; updated: string[] }; catalog: CatalogEntry[] }) => {
        setEntries(data.catalog);
        setDrafts({});
        const { added, updated } = data.result;
        setSyncMsg(
          `Added ${added.length}${added.length ? ` (${added.join(", ")})` : ""}, refreshed ${updated.length}.`,
        );
      })
      .catch((syncError) => setError(String(syncError)))
      .finally(() => setSyncing(false));
  };

  const setDraft = (agentId: string, patch: Partial<Editable>) =>
    setDrafts((all) => ({ ...all, [agentId]: { ...all[agentId], ...patch } }));

  const dirtyPatch = (entry: CatalogEntry): Partial<Editable> => {
    const draft = drafts[entry.agent_id];
    if (!draft) return {};
    const patch: Partial<Editable> = {};
    for (const key of EDITABLE_KEYS) {
      if (draft[key] !== undefined && draft[key] !== entry[key]) {
        // @ts-expect-error indexed assignment across the union is safe here
        patch[key] = draft[key];
      }
    }
    return patch;
  };

  const save = (entry: CatalogEntry) => {
    const patch = dirtyPatch(entry);
    if (Object.keys(patch).length === 0) return;
    setSavingId(entry.agent_id);
    setError(null);
    fetch(`${BACKEND_URL}/api/admin/catalog/${entry.agent_id}`, {
      method: "PATCH",
      headers: authHeaders(),
      body: JSON.stringify(patch),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
        return response.json();
      })
      .then((updated: CatalogEntry) => {
        setEntries((list) => (list ?? []).map((row) => (row.agent_id === updated.agent_id ? updated : row)));
        setDrafts((all) => {
          const next = { ...all };
          delete next[entry.agent_id];
          return next;
        });
      })
      .catch((saveError) => setError(String(saveError)))
      .finally(() => setSavingId(null));
  };

  const cell = { padding: "8px 10px", borderBottom: "1px solid var(--border)", verticalAlign: "top" } as const;
  const roCell = { ...cell, color: "var(--text-muted)" } as const;
  const input = {
    width: "100%",
    padding: "5px 7px",
    border: "1px solid var(--border)",
    borderRadius: 6,
    background: "var(--surface, #fff)",
    font: "inherit",
  } as const;

  return (
    <div>
      <div className="section-title" style={{ marginTop: 0 }}>
        Agent Catalog
        <button className="ghost-btn" onClick={sync} disabled={syncing}>
          {syncing ? "Syncing…" : "Sync from AgentCore"}
        </button>
      </div>
      <p className="hero-sub" style={{ marginBottom: 16 }}>
        Grey columns come from AgentCore and are read-only. Editable columns are
        platform-owned. Agents are discovered from AgentCore and used as-is — no
        per-agent configuration needed.
      </p>

      {syncMsg ? <p style={{ color: "var(--text-muted)" }}>{syncMsg}</p> : null}
      {error ? <p style={{ color: "var(--accent)", wordBreak: "break-word" }}>{error}</p> : null}
      {entries === null ? <p style={{ color: "var(--text-muted)" }}>Loading catalog…</p> : null}

      {entries && entries.length === 0 ? (
        <p style={{ color: "var(--text-muted)" }}>
          Catalog is empty. Click “Sync from AgentCore” to import deployed agents.
        </p>
      ) : null}

      {entries && entries.length > 0 ? (
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13, minWidth: 900 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text-muted)" }}>
                <th style={cell}>Agent</th>
                <th style={cell}>Display name</th>
                <th style={cell}>Description</th>
                <th style={cell}>Role</th>
                <th style={cell}>On</th>
                <th style={roCell}>Runtime (AgentCore)</th>
                <th style={roCell}>Protocol</th>
                <th style={roCell}>Status</th>
                <th style={roCell}>Ver</th>
                <th style={cell}></th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => {
                const draft = drafts[entry.agent_id] ?? {};
                const dirty = Object.keys(dirtyPatch(entry)).length > 0;
                return (
                  <tr key={entry.agent_id}>
                    <td style={cell}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                        <span className="agent-dot" style={{ background: agentColor(entry.agent_id) }}>
                          {entry.agent_id.slice(0, 1).toUpperCase()}
                        </span>
                        <code style={{ fontSize: 12 }}>{entry.agent_id}</code>
                      </span>
                    </td>
                    <td style={cell}>
                      <input
                        style={input}
                        value={draft.display_name ?? entry.display_name}
                        onChange={(event) => setDraft(entry.agent_id, { display_name: event.target.value })}
                      />
                    </td>
                    <td style={{ ...cell, minWidth: 220 }}>
                      <input
                        style={input}
                        value={draft.description ?? entry.description}
                        onChange={(event) => setDraft(entry.agent_id, { description: event.target.value })}
                      />
                    </td>
                    <td style={cell}>
                      <input
                        style={{ ...input, width: 90 }}
                        placeholder="—"
                        value={draft.required_role ?? entry.required_role}
                        onChange={(event) => setDraft(entry.agent_id, { required_role: event.target.value })}
                      />
                    </td>
                    <td style={{ ...cell, textAlign: "center" }}>
                      <input
                        type="checkbox"
                        checked={draft.enabled ?? entry.enabled}
                        onChange={(event) => setDraft(entry.agent_id, { enabled: event.target.checked })}
                      />
                    </td>
                    <td style={roCell} title={entry.runtime_arn}>
                      {entry.runtime_name || "—"}
                      <div style={{ fontSize: 11, opacity: 0.7 }}>…{entry.runtime_arn.slice(-16)}</div>
                    </td>
                    <td style={roCell}>
                      <span className="badge badge-blue">{entry.protocol || "?"}</span>
                    </td>
                    <td style={roCell}>
                      <span className={`badge ${entry.status === "READY" ? "badge-green" : "badge-gray"}`}>
                        {entry.status || "—"}
                      </span>
                    </td>
                    <td style={roCell}>{entry.version ? `v${entry.version}` : "—"}</td>
                    <td style={cell}>
                      <button
                        className="ghost-btn"
                        disabled={!dirty || savingId === entry.agent_id}
                        onClick={() => save(entry)}
                      >
                        {savingId === entry.agent_id ? "Saving…" : "Save"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
