import { AgentPage } from "./AgentPage";

export default async function Page({ params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = await params;
  return <AgentPage agentId={agentId} />;
}
