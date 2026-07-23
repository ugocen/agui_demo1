export const AUTH_MODE = process.env.NEXT_PUBLIC_AUTH_MODE ?? "iam";
export const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
export const ENTRA_TENANT_ID = process.env.NEXT_PUBLIC_ENTRA_TENANT_ID ?? "";
export const ENTRA_SPA_CLIENT_ID = process.env.NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID ?? "";

// Sign-in scopes. We forward a Microsoft Graph *access token* (not the ID token):
// the backend calls Graph /me with it (authoritative identity) and resolves the
// user's AD-group membership → platform roles — the AI SDLC SSO method, hardened.
// `User.Read` is enough for /me and /me/checkMemberGroups; MSAL adds openid/profile.
// Override via NEXT_PUBLIC_ENTRA_SCOPES (comma-separated) if group resolution needs
// a broader scope (e.g. add GroupMember.Read.All / Directory.Read.All).
export const ENTRA_SCOPES = (process.env.NEXT_PUBLIC_ENTRA_SCOPES ?? "User.Read")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

// The SECOND token, for agents whose AgentCore runtime does its own JWT
// validation (catalog `inbound_auth: "jwt"`). It cannot be the token above: that
// one is a Microsoft Graph access token, a first-party resource token that no
// OIDC authorizer can verify against the tenant keys.
//
// Empty (the default) = send the Entra **ID token**, which MSAL already returns
// with every silent acquisition. Its `aud` is this SPA's client id and its issuer
// is the tenant's v2.0 endpoint, so AgentCore validates it against the tenant
// discovery document with no app-registration change at all.
//
// Set it to your own API scope (e.g. "api://<api-client-id>/agent.invoke") to
// send a purpose-minted access token instead — the more orthodox choice, but it
// needs an "Expose an API" scope AND `accessTokenAcceptedVersion: 2` in that
// app's manifest, or Entra issues a v1 token whose issuer the v2.0 discovery
// document will never match.
export const ENTRA_AGENT_SCOPES = (process.env.NEXT_PUBLIC_ENTRA_AGENT_SCOPES ?? "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);
