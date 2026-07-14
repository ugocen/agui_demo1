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
// runtime deployed to AgentCore is reachable under its own id. Every agent gets
// the A2UI middleware so it can render generative UI; nothing is per-agent here.

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

type CatalogAgent = { id: string };

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

// Build the runtime + handler once (singletons keep thread state across requests).
// The agent list is resolved on the first request; restart the frontend to pick
// up newly synced agents.
let handlerSingleton: CopilotRuntimeFetchHandler | null = null;

async function handler(request: Request): Promise<Response> {
  if (!handlerSingleton) {
    const catalog = await fetchCatalogAgents(request.headers.get("authorization"));
    const agentIds = catalog.map((agent) => agent.id);

    const runtime = new CopilotRuntime({
      agents: ({ request: agentRequest }: { request: Request }) => {
        const authorization = agentRequest.headers.get("authorization");
        const headers: Record<string, string> = authorization ? { Authorization: authorization } : {};
        // One HttpAgent per catalog id -> the AG-UI proxy route for that id.
        return Object.fromEntries(
          agentIds.map((id) => [id, new HttpAgent({ url: `${BACKEND_URL}/api/agui/${id}`, headers })]),
        );
      },
      // First-class A2UI for EVERY agent: auto-apply A2UIMiddleware (injects the
      // render_a2ui tool + component catalog so the agent's LLM can emit A2UI v0.9
      // surfaces) and signal the client via /info to mount the A2UI renderer.
      ...(agentIds.length > 0 ? { a2ui: { agents: agentIds, injectA2UITool: true } } : {}),
    });
    handlerSingleton = createCopilotRuntimeHandler({ runtime, basePath: "/api/copilotkit" });
  }
  return handlerSingleton(request);
}

export const GET = handler;
export const POST = handler;
export const DELETE = handler;
