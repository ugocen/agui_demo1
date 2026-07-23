import { HttpAgent } from "@ag-ui/client";
import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
  type CopilotRuntimeFetchHandler,
} from "@copilotkit/runtime/v2";

// Self-hosted CopilotKit runtime: agents are registered server-side and point at
// the FastAPI AG-UI proxy. The caller's Authorization header (entra mode) is
// forwarded to the backend. The agent list is built DYNAMICALLY from the backend
// catalog (`/api/agents`, synced from AgentCore) — no hardcoded ids — so any
// runtime deployed to AgentCore is reachable under its own id. Nothing here is
// per-agent code: the only thing read per agent is its catalog `ui_mode`.
//
// This is also where a `ui_mode: "static"` agent is actually kept away from A2UI.
// The runtime's A2UIMiddleware injects the `render_a2ui` tool into an agent's LLM,
// so only agents whose catalog entry says "a2ui" are listed below. Leaving a static
// agent in that list would hand its model a second, competing way to draw — and
// nothing on the client can undo that once the tool is in the prompt.

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

type CatalogAgent = { id: string; ui_mode?: string };

/** The backend's registered, enabled agents (DB catalog, joined to AgentCore). */
async function fetchCatalogAgents(authorization: string | null): Promise<CatalogAgent[]> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/agents`, {
      headers: authorization ? { Authorization: authorization } : {},
    });
    if (!response.ok) return [];
    return (await response.json()) as CatalogAgent[];
  } catch {
    return [];
  }
}

// The runtime + handler are cached (they hold thread state across requests) and
// rebuilt only when the catalog's shape changes — its agent ids, or their ui_mode.
//
// This was previously built once on the first request and kept forever, which meant
// an admin flipping ui_mode in /admin changed nothing until the frontend process was
// restarted: the switch would have been a lie in exactly the way it is now meant to
// stop being one. Re-reading the catalog costs one local call per request (Route
// Handlers and `fetch` are both uncached by default, so this really does re-read),
// and thread state is dropped only when the catalog actually changed.
let cached: { key: string; handler: CopilotRuntimeFetchHandler } | null = null;

// A failed read (backend restarting, a momentary 401) must not tear down a working
// runtime, so the last good catalog is kept and reused.
let lastGoodCatalog: CatalogAgent[] = [];

async function handler(request: Request): Promise<Response> {
  const fresh = await fetchCatalogAgents(request.headers.get("authorization"));
  if (fresh.length > 0) lastGoodCatalog = fresh;
  const catalog = lastGoodCatalog;

  const agentIds = catalog.map((agent) => agent.id);
  // A missing/unknown ui_mode falls to A2UI, matching the DB column's own default,
  // so an older catalog payload keeps behaving exactly as it does today.
  const a2uiIds = catalog.filter((agent) => agent.ui_mode !== "static").map((agent) => agent.id);
  const key = JSON.stringify([agentIds, a2uiIds]);

  if (!cached || cached.key !== key) {
    const runtime = new CopilotRuntime({
      agents: ({ request: agentRequest }: { request: Request }) => {
        const authorization = agentRequest.headers.get("authorization");
        // The second token, for agents on a JWT-authorized AgentCore runtime.
        // The runtime rejects the platform's own bearer (a Graph access token is
        // not verifiable by an OIDC authorizer), so the browser sends a
        // tenant-issued one alongside it and the proxy forwards THAT upstream.
        const agentAuthorization = agentRequest.headers.get("x-agent-authorization");
        const headers: Record<string, string> = {
          ...(authorization ? { Authorization: authorization } : {}),
          ...(agentAuthorization ? { "X-Agent-Authorization": agentAuthorization } : {}),
        };
        // One HttpAgent per catalog id -> the AG-UI proxy route for that id.
        return Object.fromEntries(
          agentIds.map((id) => [id, new HttpAgent({ url: `${BACKEND_URL}/api/agui/${id}`, headers })]),
        );
      },
      // A2UI for the agents that asked for it: auto-apply A2UIMiddleware (injects
      // the render_a2ui tool + component catalog so the agent's LLM can emit A2UI
      // v0.9 surfaces) and signal the client via /info to mount the A2UI renderer.
      ...(a2uiIds.length > 0 ? { a2ui: { agents: a2uiIds, injectA2UITool: true } } : {}),
    });
    cached = { key, handler: createCopilotRuntimeHandler({ runtime, basePath: "/api/copilotkit" }) };
  }
  return cached.handler(request);
}

export const GET = handler;
export const POST = handler;
export const DELETE = handler;
