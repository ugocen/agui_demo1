"use client";

import { InteractionRequiredAuthError } from "@azure/msal-browser";
import { MsalProvider, useIsAuthenticated, useMsal } from "@azure/msal-react";
import { createContext, useContext, useEffect, useState } from "react";

import { AUTH_MODE, BACKEND_URL, ENTRA_AGENT_SCOPES, ENTRA_SCOPES } from "@/lib/config";
import { msalInstance } from "@/lib/msal";

const TokenContext = createContext<string | null>(null);

export function useAccessToken(): string | null {
  return useContext(TokenContext);
}

const AgentTokenContext = createContext<string | null>(null);

/** The tenant-issued token for agents whose AgentCore runtime validates JWTs
 *  itself. Sent as `X-Agent-Authorization` beside the platform's own bearer —
 *  see ENTRA_AGENT_SCOPES in lib/config for why one token cannot serve both. */
export function useAgentToken(): string | null {
  return useContext(AgentTokenContext);
}

/** The backend's authoritative view of the caller. Roles are computed server-side
 *  from live AD-group membership; the client only mirrors them for UI. Never make
 *  an authorization decision from this alone — the backend enforces it. */
export type Me = {
  mode: string;
  authenticated: boolean;
  user: string | null;
  email: string | null;
  roles: string[];
};

const IAM_ME: Me = { mode: "iam", authenticated: false, user: null, email: null, roles: [] };

const MeContext = createContext<Me>(IAM_ME);

export function useMe(): Me {
  return useContext(MeContext);
}

/** UI-only role check (show/hide). Real enforcement lives on the backend. */
export function useHasRole(role: string): boolean {
  return useContext(MeContext).roles.includes(role);
}

function EntraGate({ children }: { children: React.ReactNode }) {
  const { instance, accounts } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const [token, setToken] = useState<string | null>(null);
  const [agentToken, setAgentToken] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated || accounts.length === 0) {
      return;
    }
    instance
      .acquireTokenSilent({ scopes: ENTRA_SCOPES, account: accounts[0] })
      // We forward the Microsoft Graph *access token* (aud = Graph): the backend
      // calls Graph /me with it (authoritative identity) and resolves AD-group
      // roles. This is the AI SDLC SSO method, hardened with tenant/client pinning.
      .then((result) => {
        setToken(result.accessToken);
        // The ID token comes back with the same silent acquisition and is
        // refreshed with it, so the default agent token costs no extra call.
        if (ENTRA_AGENT_SCOPES.length === 0) setAgentToken(result.idToken ?? null);
      })
      .catch((silentError) => {
        if (silentError instanceof InteractionRequiredAuthError) {
          instance.acquireTokenRedirect({ scopes: ENTRA_SCOPES });
          return;
        }
        setError(String(silentError));
      });
  }, [instance, accounts, isAuthenticated]);

  // A dedicated API scope was configured, so mint that access token separately.
  // A failure here is NOT fatal: it only costs the JWT-authorized agents, and
  // failing the whole sign-in over one optional scope would take the other five
  // agents down with it.
  useEffect(() => {
    if (!isAuthenticated || accounts.length === 0 || ENTRA_AGENT_SCOPES.length === 0) {
      return;
    }
    instance
      .acquireTokenSilent({ scopes: ENTRA_AGENT_SCOPES, account: accounts[0] })
      .then((result) => setAgentToken(result.accessToken))
      .catch((silentError) => {
        if (silentError instanceof InteractionRequiredAuthError) {
          instance.acquireTokenRedirect({ scopes: ENTRA_AGENT_SCOPES });
          return;
        }
        console.warn("could not acquire the agent token", silentError);
      });
  }, [instance, accounts, isAuthenticated]);

  // Ask the backend who it thinks we are and what roles we have (source of truth).
  useEffect(() => {
    if (!token) {
      return;
    }
    let cancelled = false;
    fetch(`${BACKEND_URL}/api/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => (response.ok ? response.json() : null))
      .then((data: Me | null) => {
        if (!cancelled && data) {
          setMe(data);
        }
      })
      .catch(() => {
        // Leave roles empty on failure — UI degrades to "no role", never elevates.
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (!isAuthenticated) {
    return (
      <div className="signin-screen">
        <div className="signin-card">
          <span className="brand-mark" style={{ width: 44, height: 44, fontSize: 18 }}>
            GU
          </span>
          <h1>Generative UI demo for AI SDLC</h1>
          <p>Sign in with your Microsoft Entra ID account to continue.</p>
          <button
            className="signin-btn"
            onClick={() => instance.loginRedirect({ scopes: ENTRA_SCOPES })}
          >
            Sign in with Microsoft
          </button>
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="signin-screen">
        <div className="signin-card">
          <h1>Sign-in error</h1>
          <p style={{ color: "var(--accent)", wordBreak: "break-word" }}>{error}</p>
        </div>
      </div>
    );
  }
  if (!token) {
    return (
      <div className="signin-screen">
        <div className="signin-card">
          <p>Acquiring token…</p>
        </div>
      </div>
    );
  }
  const meValue: Me =
    me ?? {
      mode: "entra",
      authenticated: true,
      user: accounts[0]?.name ?? null,
      email: accounts[0]?.username ?? null,
      roles: [],
    };
  return (
    <TokenContext.Provider value={token}>
      <AgentTokenContext.Provider value={agentToken}>
        <MeContext.Provider value={meValue}>{children}</MeContext.Provider>
      </AgentTokenContext.Provider>
    </TokenContext.Provider>
  );
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  if (AUTH_MODE !== "entra") {
    return (
      <TokenContext.Provider value={null}>
        <AgentTokenContext.Provider value={null}>
          <MeContext.Provider value={IAM_ME}>{children}</MeContext.Provider>
        </AgentTokenContext.Provider>
      </TokenContext.Provider>
    );
  }
  return (
    <MsalProvider instance={msalInstance}>
      <EntraGate>{children}</EntraGate>
    </MsalProvider>
  );
}
