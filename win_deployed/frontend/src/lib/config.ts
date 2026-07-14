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
