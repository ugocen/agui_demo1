"use client";

/**
 * Static card catalog — the `ui_mode: "static"` half of the platform's two
 * rendering strategies. The A2UI half is `a2ui/richCatalog.tsx`.
 *
 * Keyed by TOOL NAME, never by agent id: anything that calls `show_user_stories`
 * gets the story cards, whether that is today's SDLC planner or a runtime deployed
 * to AgentCore tomorrow. Adding a card means adding an entry here — the same
 * extension-point rule richCatalog follows for A2UI (AGENTS.md invariant 5). The
 * version deleted in f98cff8 keyed off `agentId === "planner"`, which is what made
 * it per-agent code and is not how this one works.
 *
 * `useRenderTool` only RENDERS. It defines no tool and tells the model nothing —
 * every tool below is owned by its agent's backend (Strands `@tool`, or LangGraph's
 * `manually_emit_tool_call`). Frontend-owned tools that PAUSE the run live in
 * `hitl/HumanInTheLoop.tsx` and are mounted in BOTH ui_modes: they are a protocol
 * contract (`bug-report` ships `tools=[]` and cannot run without them), not a
 * rendering style.
 *
 * `parameters` ARRIVES PARTIAL. CopilotKit renders on TOOL_CALL_START and the
 * arguments stream in as TOOL_CALL_ARGS deltas — the types encode this
 * (`status: "inProgress"` → `Partial<…>`). Every card reads `parameters` directly
 * in render and shows a placeholder while it is still empty; none of them seed
 * state from it.
 *
 * Schemas are `zod/v3`, matching richCatalog and HumanInTheLoop. Here they only
 * type `props.parameters` — nothing is sent to the model.
 */

import { useRenderTool } from "@copilotkit/react-core/v2";
import { z } from "zod/v3";

import { ChecklistCard } from "@/components/cards/ChecklistCard";
import { ChecklistScorecard } from "@/components/cards/ChecklistScorecard";
import { CompletenessCard } from "@/components/cards/CompletenessCard";
import { DesignContextCard } from "@/components/cards/DesignContextCard";
import { EstimateTable } from "@/components/cards/EstimateTable";
import { IntakeSummaryCard } from "@/components/cards/IntakeSummaryCard";
import { JiraArtifactCard } from "@/components/cards/JiraArtifactCard";
import { RiskMatrixCard } from "@/components/cards/RiskMatrixCard";
import { StoryCard } from "@/components/cards/StoryCard";
import { StoryCriteriaCard } from "@/components/cards/StoryCriteriaCard";
import { StoryReportCard } from "@/components/cards/StoryReportCard";

// Payload shapes mirror the agents' tool signatures:
//   agents/sdlc-planner-strands/tools.py         → show_user_stories, show_estimates
//   agents/release-readiness-langgraph/graph.py  → show_release_checklist, show_risk_matrix
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

const checklistSchema = z.object({
  release: z.string(),
  items: z.array(z.object({ name: z.string(), status: z.string(), detail: z.string() })),
});

const riskMatrixSchema = z.object({
  risks: z.array(
    z.object({
      name: z.string(),
      probability: z.number(),
      impact: z.number(),
      mitigation: z.string(),
    })
  ),
});

//   agents/jira-story-strands/tools.py → show_intake_summary, show_design_context,
//   show_story_and_criteria, show_completeness_findings, show_checklist_scorecard,
//   show_story_report, publish_jira_story
const intakeSchema = z.object({
  persona: z.string(),
  goal: z.string(),
  benefit: z.string(),
  problem_statement: z.string(),
  targets_a_screen: z.boolean(),
  user_supplied_ac_count: z.number(),
  backend_notes: z.array(z.string()),
  frontend_notes: z.array(z.string()),
  infra_notes: z.array(z.string()),
  transcription_flags: z.array(
    z.object({ token: z.string(), guess: z.string(), why: z.string() })
  ),
});

const designContextSchema = z.object({
  screen_name: z.string(),
  fields_and_controls: z.array(z.string()),
  visible_states: z.array(z.string()),
  visible_messages: z.array(z.string()),
  lists_or_tables: z.array(z.string()),
  roles_or_modes: z.array(z.string()),
  uncertain: z.array(z.string()),
});

const criterionSchema = z.object({
  title: z.string(),
  given: z.array(z.string()),
  when: z.array(z.string()),
  then: z.array(z.string()),
  but: z.array(z.string()),
  source: z.string(),
  status: z.string(),
});

const storyCriteriaSchema = z.object({
  persona: z.string(),
  goal: z.string(),
  benefit: z.string(),
  coverage: z.string(),
  acceptance_criteria: z.array(criterionSchema),
});

const completenessSchema = z.object({
  findings: z.array(
    z.object({
      ac_id: z.string(),
      category: z.number(),
      gap: z.string(),
      is_mechanical: z.boolean(),
      resolution: z.string(),
    })
  ),
});

const scorecardSchema = z.object({
  items: z.array(z.object({ item_id: z.number(), status: z.string(), reason: z.string() })),
  loop: z.number(),
});

const storyReportSchema = z.object({
  changes_made: z.array(z.string()),
  open_business_decisions: z.array(
    z.object({
      question: z.string(),
      recommended_default: z.string(),
      context: z.string(),
      blocking: z.boolean(),
    })
  ),
  recommendations: z.array(z.string()),
});

// The artifact card is the one entry that reads the tool's RESULT rather than its
// arguments: the Jira markup is rendered by Python (so a model cannot drift on the
// format) and therefore exists only on the way back. The schema here is nominal.
const publishSchema = z.object({ title: z.string() });

/**
 * Registers every static tool card. Mount inside <CopilotKitProvider>, next to
 * <FallbackRender />, for agents whose catalog ui_mode is "static".
 */
export function CardCatalog() {
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

  useRenderTool(
    {
      name: "show_release_checklist",
      parameters: checklistSchema,
      render: ({ parameters }) => (
        <ChecklistCard release={parameters.release} items={parameters.items} />
      ),
    },
    []
  );

  useRenderTool(
    {
      name: "show_risk_matrix",
      parameters: riskMatrixSchema,
      render: ({ parameters }) => <RiskMatrixCard risks={parameters.risks} />,
    },
    []
  );

  useRenderTool(
    {
      name: "show_intake_summary",
      parameters: intakeSchema,
      render: ({ parameters }) => <IntakeSummaryCard {...parameters} />,
    },
    []
  );

  useRenderTool(
    {
      name: "show_design_context",
      parameters: designContextSchema,
      render: ({ parameters }) => <DesignContextCard {...parameters} />,
    },
    []
  );

  useRenderTool(
    {
      name: "show_story_and_criteria",
      parameters: storyCriteriaSchema,
      render: ({ parameters }) => <StoryCriteriaCard {...parameters} />,
    },
    []
  );

  useRenderTool(
    {
      name: "show_completeness_findings",
      parameters: completenessSchema,
      render: ({ parameters }) => <CompletenessCard findings={parameters.findings} />,
    },
    []
  );

  useRenderTool(
    {
      name: "show_checklist_scorecard",
      parameters: scorecardSchema,
      render: ({ parameters }) => (
        <ChecklistScorecard items={parameters.items} loop={parameters.loop} />
      ),
    },
    []
  );

  useRenderTool(
    {
      name: "show_story_report",
      parameters: storyReportSchema,
      render: ({ parameters }) => <StoryReportCard {...parameters} />,
    },
    []
  );

  useRenderTool(
    {
      name: "publish_jira_story",
      parameters: publishSchema,
      render: ({ toolCallId, result }) => (
        <JiraArtifactCard toolCallId={toolCallId} result={result} />
      ),
    },
    []
  );

  return null;
}
