"use client";

import {
  CopilotChat,
  CopilotKitProvider,
  useAgent,
  UseAgentUpdate,
  useConfigureSuggestions,
  useDefaultRenderTool,
  useHumanInTheLoop,
  useInterrupt,
  useRenderTool,
} from "@copilotkit/react-core/v2";
import "@copilotkit/react-core/v2/styles.css";
import { useEffect, useState } from "react";
import { z } from "zod";

import { updateThreadTitle, upsertThread } from "@/lib/threads";

import { useAccessToken } from "@/components/AuthGate";
import { richCatalog } from "@/components/a2ui/richCatalog";
import { BugCanvasPanel, BugCanvasProvider, useBugCanvas } from "@/components/canvas/BugCanvas";
import { PressCanvasPanel, PressCanvasProvider, usePressCanvas } from "@/components/canvas/PressCanvas";
import { ApprovalCard } from "@/components/cards/ApprovalCard";
import { BugReportForm } from "@/components/cards/BugReportForm";
import { ChecklistCard } from "@/components/cards/ChecklistCard";
import { ChoiceCard } from "@/components/cards/ChoiceCard";
import { DecisionCard } from "@/components/cards/DecisionCard";
import { EstimateTable } from "@/components/cards/EstimateTable";
import { PressReleaseForm } from "@/components/cards/PressReleaseForm";
import { ProgressIndicator } from "@/components/cards/ProgressIndicator";
import { RiskMatrixCard } from "@/components/cards/RiskMatrixCard";
import { StoryCard } from "@/components/cards/StoryCard";

const storySchema = z.object({
  stories: z.array(
    z.object({
      id: z.string(),
      title: z.string(),
      acceptance_criteria: z.array(z.string()),
      priority: z.enum(["high", "medium", "low"]),
    })
  ),
});

const estimateSchema = z.object({
  items: z.array(
    z.object({
      story_id: z.string(),
      points: z.number(),
      confidence: z.enum(["high", "medium", "low"]),
    })
  ),
});

const approvalSchema = z.object({
  summary: z.string().describe("One sentence summary of what will be created"),
  tickets: z.array(
    z.object({
      title: z.string(),
      points: z.number(),
    })
  ),
});

const checklistSchema = z.object({
  release: z.string(),
  items: z.array(
    z.object({
      name: z.string(),
      status: z.enum(["pass", "fail", "warn"]),
      detail: z.string(),
    })
  ),
});

const riskSchema = z.object({
  risks: z.array(
    z.object({
      name: z.string(),
      probability: z.number(),
      impact: z.number(),
      mitigation: z.string(),
    })
  ),
});

const bugReportSchema = z.object({
  title: z.string(),
  severity: z.enum(["critical", "high", "medium", "low"]),
  steps_to_reproduce: z.string(),
  expected_behavior: z.string(),
  actual_behavior: z.string(),
  environment: z.string(),
});

const pressReleaseSchema = z.object({
  headline: z.string(),
  subheadline: z.string().optional(),
  dateline: z.string().optional(),
  body: z.string(),
  boilerplate: z.string().optional(),
  contact: z.string().optional(),
});

const choiceSchema = z.object({
  question: z.string(),
  options: z.array(z.string()),
});

function PlannerCards() {
  useRenderTool(
    {
      name: "show_user_stories",
      parameters: storySchema,
      render: ({ parameters }) => <StoryCard stories={parameters.stories} />,
    },
    []
  );
  useRenderTool(
    {
      name: "show_estimates",
      parameters: estimateSchema,
      render: ({ parameters }) => <EstimateTable items={parameters.items} />,
    },
    []
  );
  useHumanInTheLoop(
    {
      name: "request_ticket_approval",
      description:
        "Ask the human to approve or reject ticket creation before any ticket is created. Returns the decision.",
      parameters: approvalSchema,
      render: (props) => (
        <ApprovalCard
          summary={props.args.summary}
          tickets={props.args.tickets}
          respond={props.respond}
          result={props.result}
        />
      ),
    },
    []
  );
  return null;
}

function ReleaseCards({ agentId }: { agentId: string }) {
  useRenderTool(
    {
      name: "show_release_checklist",
      parameters: checklistSchema,
      render: ({ parameters }) => <ChecklistCard release={parameters.release} items={parameters.items} />,
    },
    []
  );
  useRenderTool(
    {
      name: "show_risk_matrix",
      parameters: riskSchema,
      render: ({ parameters }) => <RiskMatrixCard risks={parameters.risks} />,
    },
    []
  );
  useInterrupt(
    {
      agentId,
      render: ({ event, resolve }) => {
        let payload: Record<string, unknown> = {};
        const raw = event?.value;
        if (typeof raw === "string") {
          try {
            payload = JSON.parse(raw);
          } catch {
            payload = { recommendation: raw };
          }
        } else if (raw && typeof raw === "object") {
          payload = raw as Record<string, unknown>;
        }
        return <DecisionCard payload={payload} resolve={resolve} />;
      },
    }
  );
  return null;
}

function BugReportCards() {
  const { showBug } = useBugCanvas();
  useHumanInTheLoop(
    {
      name: "draft_bug_report",
      description:
        "Propose a structured bug report for the user to review, edit, and submit. Returns the submitted report.",
      parameters: bugReportSchema,
      render: (props) => (
        <BugReportForm
          proposed={props.args}
          respond={props.respond}
          result={props.result}
          onSubmit={showBug}
        />
      ),
    },
    [showBug]
  );
  return null;
}

function PressReleaseCards() {
  const { showPress } = usePressCanvas();
  useHumanInTheLoop(
    {
      name: "draft_press_release",
      description:
        "Propose a press release for the user to review, edit, and submit. Returns the submitted release.",
      parameters: pressReleaseSchema,
      render: (props) => (
        <PressReleaseForm
          proposed={props.args}
          respond={props.respond}
          result={props.result}
          onSubmit={showPress}
        />
      ),
    },
    [showPress]
  );
  useHumanInTheLoop(
    {
      name: "ask_choice",
      description:
        "Ask the user a multiple-choice question they answer by clicking one option. Returns the chosen option.",
      parameters: choiceSchema,
      render: (props) => (
        <ChoiceCard
          question={props.args.question ?? ""}
          options={props.args.options ?? []}
          respond={props.respond}
          result={props.result}
        />
      ),
    },
    []
  );
  return null;
}

// For agents whose catalog ui_mode is "a2ui", the runtime applies the A2UI
// middleware (see app/api/copilotkit/route.ts) and CopilotKit mounts the A2UI
// renderer itself via /info — so we simply do NOT mount our hand-authored cards.
function FallbackRender() {
  useDefaultRenderTool(
    {
      render: ({ name, status }) => (
        <div style={{ padding: 6, color: "#888", fontSize: 13 }}>
          {status === "complete" ? "✓" : "⏳"} tool: {name}
        </div>
      ),
    },
    []
  );
  return null;
}

function ReleaseProgress({ agentId }: { agentId: string }) {
  const { agent } = useAgent({ agentId });
  const progress = (agent?.state as { progress?: { step?: number; total?: number; label?: string } })
    ?.progress;
  return <ProgressIndicator progress={progress} />;
}

const STARTER_PROMPTS: Record<string, { title: string; message: string }[]> = {
  planner: [
    {
      title: "Draft user stories",
      message: "Generate user stories for a password reset feature",
    },
    { title: "Estimate the backlog", message: "Estimate the current stories" },
    {
      title: "Create tickets",
      message: "Create tickets for the stories you drafted",
    },
  ],
  release: [
    {
      title: "Assess a release",
      message: "Assess release readiness for version 1.4.0",
    },
  ],
  bugreport: [
    {
      title: "File a bug",
      message: "The password reset link returns a 500 error on the login page in Chrome",
    },
  ],
  a2uidemo: [
    { title: "Plan a login feature", message: "Plan a login feature for our app" },
    { title: "Show a signup form", message: "Show me a signup form with name and email" },
  ],
  pressrelease: [
    {
      title: "Product launch",
      message: "Write a press release announcing our new AI-powered analytics dashboard, launching next month",
    },
    { title: "Funding round", message: "Write a press release about our $10M Series A funding round" },
  ],
};

function AgentSuggestions({ agentId }: { agentId: string }) {
  const prompts = STARTER_PROMPTS[agentId];
  useConfigureSuggestions(
    prompts
      ? { suggestions: prompts, available: "before-first-message", consumerAgentId: agentId }
      : null,
    [agentId]
  );
  return null;
}

function EventInspector({ agentId }: { agentId: string }) {
  useAgent({
    agentId,
    updates: [UseAgentUpdate.OnStateChanged, UseAgentUpdate.OnMessagesChanged],
  });
  const { agent } = useAgent({ agentId });
  const state = agent?.state ?? {};
  const messages = (agent?.messages ?? []) as { role?: string }[];
  const isRunning = Boolean(agent?.isRunning);

  const roleCounts = messages.reduce<Record<string, number>>((acc, message) => {
    const role = message.role ?? "unknown";
    acc[role] = (acc[role] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <aside className="inspector">
      <div className="inspector-title">
        AG-UI live state
        <span className={`inspector-run ${isRunning ? "on" : ""}`}>
          {isRunning ? "running" : "idle"}
        </span>
      </div>
      <div className="inspector-label">messages</div>
      <div className="inspector-counts">
        {Object.entries(roleCounts).map(([role, count]) => (
          <span key={role} className="badge badge-gray">
            {role}: {count}
          </span>
        ))}
        {messages.length === 0 ? <span className="inspector-empty">none yet</span> : null}
      </div>
      <div className="inspector-label">shared state</div>
      <pre className="inspector-json">
        {Object.keys(state).length ? JSON.stringify(state, null, 2) : "{}"}
      </pre>
    </aside>
  );
}

function ThreadTitleTracker({ agentId, threadId }: { agentId: string; threadId: string }) {
  useAgent({ agentId, updates: [UseAgentUpdate.OnMessagesChanged] });
  const { agent } = useAgent({ agentId });
  useEffect(() => {
    const messages = (agent?.messages ?? []) as { role?: string; content?: unknown }[];
    const firstUser = messages.find((message) => message.role === "user");
    if (firstUser && typeof firstUser.content === "string") {
      updateThreadTitle(threadId, firstUser.content);
    }
  });
  return null;
}

export function AgentChat({
  agentId,
  agentName,
  threadId,
  uiMode = "static",
}: {
  agentId: string;
  agentName: string;
  threadId: string;
  uiMode?: "static" | "a2ui";
}) {
  const token = useAccessToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

  useEffect(() => {
    upsertThread({
      id: threadId,
      agentId,
      agentName,
      title: agentName,
      createdAt: Date.now(),
    });
  }, [threadId, agentId, agentName]);

  const [inspectorOpen, setInspectorOpen] = useState(false);

  return (
    <CopilotKitProvider
      runtimeUrl="/api/copilotkit"
      headers={headers}
      // Render A2UI surfaces with the rich catalog (basic + Mermaid/Chart/Markdown/Html)
      // and send its component schemas to the agent so the LLM knows they exist.
      a2ui={{ catalog: richCatalog, includeSchema: true }}
    >
      <BugCanvasProvider>
      <PressCanvasProvider>
        <FallbackRender />
        <AgentSuggestions agentId={agentId} />
        {uiMode === "a2ui" ? null : (
          <>
            {agentId === "planner" ? <PlannerCards /> : null}
            {agentId === "release" ? <ReleaseCards agentId={agentId} /> : null}
            {agentId === "bugreport" ? <BugReportCards /> : null}
            {agentId === "pressrelease" ? <PressReleaseCards /> : null}
          </>
        )}
        <ThreadTitleTracker agentId={agentId} threadId={threadId} />
        <div className="chat-body">
          <div className="chat-region">
            <div className="chat-toolbar">
              {agentId === "release" ? (
                <div className="progress-strip">
                  <ReleaseProgress agentId={agentId} />
                </div>
              ) : (
                <span />
              )}
              <button
                className="ghost-btn"
                onClick={() => setInspectorOpen((open) => !open)}
                title="Inspect the live AG-UI state and message stream"
              >
                {inspectorOpen ? "Hide inspector" : "Inspect state"}
              </button>
            </div>
            <div className="chat-host">
              <CopilotChat key={threadId} agentId={agentId} threadId={threadId} />
            </div>
          </div>
          {agentId === "bugreport" ? <BugCanvasPanel /> : null}
          {agentId === "pressrelease" ? <PressCanvasPanel /> : null}
          {inspectorOpen ? <EventInspector agentId={agentId} /> : null}
        </div>
      </PressCanvasProvider>
      </BugCanvasProvider>
    </CopilotKitProvider>
  );
}
