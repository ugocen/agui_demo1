import { AgentPage } from "./AgentPage";

const AGENT_NAMES: Record<string, string> = {
  planner: "SDLC Planner",
  release: "Release Readiness",
  bugreport: "Bug Report Assistant",
  a2uidemo: "A2UI Demo",
  pressrelease: "Press Release Assistant",
};

export default async function Page({ params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = await params;
  return <AgentPage agentId={agentId} agentName={AGENT_NAMES[agentId] ?? agentId} />;
}
