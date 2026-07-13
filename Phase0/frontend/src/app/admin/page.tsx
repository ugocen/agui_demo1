"use client";

import { Suspense } from "react";

import { AgentCatalogAdmin } from "@/components/admin/AgentCatalogAdmin";
import { AuthGate, useMe } from "@/components/AuthGate";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";

function AdminInner() {
  const me = useMe();
  // UI gate only — the backend enforces admin on every /api/admin call.
  // In iam mode (SSO off) there are no roles, so the screen is open for local dev.
  const isAdmin = me.mode !== "entra" || me.roles.includes("admin");

  return (
    <WorkspaceShell>
      <div className="home-main">
        <div className="home-container">
          <div className="hero-title">Admin · Settings</div>
          <p className="hero-sub">Platform configuration.</p>
          {isAdmin ? (
            <AgentCatalogAdmin />
          ) : (
            <p style={{ color: "var(--accent)" }}>
              This page requires the <strong>admin</strong> role. Signed in as{" "}
              {me.email ?? me.user ?? "unknown"}
              {me.roles.length ? ` (roles: ${me.roles.join(", ")})` : " (no roles)"}.
            </p>
          )}
        </div>
      </div>
    </WorkspaceShell>
  );
}

export default function AdminPage() {
  return (
    <AuthGate>
      <Suspense fallback={null}>
        <AdminInner />
      </Suspense>
    </AuthGate>
  );
}
