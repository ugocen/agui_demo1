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
import { EstimateTable } from "@/components/cards/EstimateTable";
import { RiskMatrixCard } from "@/components/cards/RiskMatrixCard";
import { StoryCard } from "@/components/cards/StoryCard";

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

  return null;
}
