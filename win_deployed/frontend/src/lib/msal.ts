import { PublicClientApplication } from "@azure/msal-browser";

import { ENTRA_SPA_CLIENT_ID, ENTRA_TENANT_ID } from "./config";

export const msalInstance = new PublicClientApplication({
  auth: {
    clientId: ENTRA_SPA_CLIENT_ID,
    authority: `https://login.microsoftonline.com/${ENTRA_TENANT_ID}`,
    redirectUri: typeof window === "undefined" ? "/" : window.location.origin,
  },
  cache: {
    cacheLocation: "sessionStorage",
  },
});
