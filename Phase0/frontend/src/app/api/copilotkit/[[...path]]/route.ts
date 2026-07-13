import { HttpAgent } from "@ag-ui/client";
import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
  type CopilotRuntimeFetchHandler,
} from "@copilotkit/runtime/v2";

// Self-hosted CopilotKit runtime: agents are registered server-side and point at
// the FastAPI AG-UI proxy. The caller's Authorization header (entra mode) is
// forwarded to the backend. Agents the catalog marks as ui_mode=a2ui get the
// A2UI middleware applied automatically (see below).

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

/** Ask the backend which registered agents are ui_mode=a2ui (joined by the catalog). */
async function a2uiAgentIds(authorization: string | null): Promise<string[]> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/agents`, {
      headers: authorization ? { Authorization: authorization } : {},
    });
    if (!response.ok) return [];
    const agents = (await response.json()) as { id: string; ui_mode?: string }[];
    return agents.filter((agent) => agent.ui_mode === "a2ui").map((agent) => agent.id);
  } catch {
    return [];
  }
}

// Build the runtime + handler once (singletons keep thread state across requests).
// The a2ui agent list is resolved on the first request; restart to pick up admin
// changes to ui_mode.
let handlerSingleton: CopilotRuntimeFetchHandler | null = null;

async function handler(request: Request): Promise<Response> {
  if (!handlerSingleton) {
    const a2ui = await a2uiAgentIds(request.headers.get("authorization"));
    const runtime = new CopilotRuntime({
      agents: ({ request: agentRequest }: { request: Request }) => {
        const authorization = agentRequest.headers.get("authorization");
        const headers: Record<string, string> = authorization ? { Authorization: authorization } : {};
        return {
          planner: new HttpAgent({ url: `${BACKEND_URL}/api/agui/planner`, headers }),
          release: new HttpAgent({ url: `${BACKEND_URL}/api/agui/release`, headers }),
          bugreport: new HttpAgent({ url: `${BACKEND_URL}/api/agui/bugreport`, headers }),
          a2uidemo: new HttpAgent({ url: `${BACKEND_URL}/api/agui/a2uidemo`, headers }),
          pressrelease: new HttpAgent({ url: `${BACKEND_URL}/api/agui/pressrelease`, headers }),
        };
      },
      // First-class A2UI: auto-apply A2UIMiddleware to these agents (injects the
      // render_a2ui tool + component catalog so the agent's LLM emits A2UI v0.9
      // surfaces) and signal the client via /info to mount the A2UI renderer.
      ...(a2ui.length > 0 ? { a2ui: { agents: a2ui, injectA2UITool: true } } : {}),
    });
    handlerSingleton = createCopilotRuntimeHandler({ runtime, basePath: "/api/copilotkit" });
  }
  return handlerSingleton(request);
}

export const GET = handler;
export const POST = handler;
export const DELETE = handler;
