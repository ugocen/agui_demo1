"use client";

/**
 * Progress strip driven by AG-UI STATE, not by the model.
 *
 * An agent that declares `state.pipeline` gets a stepper above its chat; every
 * other agent renders nothing at all. That is what keeps it generic (AGENTS.md
 * invariant 5) — there is no agent id here, only a shape an agent may opt into:
 *
 *   state.pipeline = { steps: [{id, label}, …], done: ["intake", …], current: "publish" }
 *
 * Why state rather than a "show_progress" tool: a tool call is the model
 * NARRATING its progress, which costs a round trip and can be wrong about
 * itself. This state is written by the adapter's `state_from_args` /
 * `state_from_result` hooks at the moment a tool actually starts and finishes,
 * so it reports what happened rather than what the model believes happened.
 *
 * Note the adapter emits whole-object STATE_SNAPSHOTs and never STATE_DELTA, so
 * the payload here is always complete — there is nothing to merge.
 */

import { useAgent, UseAgentUpdate } from "@copilotkit/react-core/v2";

type Step = { id?: string; label?: string };
type Pipeline = { steps?: Step[]; done?: string[]; current?: string };

export function RunTimeline({ agentId }: { agentId: string }) {
  // Subscribing and reading are two separate calls, matching the inspector: the
  // first registers interest in state changes, the second reads the agent.
  useAgent({ agentId, updates: [UseAgentUpdate.OnStateChanged] });
  const { agent } = useAgent({ agentId });

  const state = (agent?.state ?? {}) as { pipeline?: Pipeline };
  const pipeline = state.pipeline;
  const steps = (pipeline?.steps ?? []).filter((step) => step?.id);
  if (steps.length === 0) return null;

  const done = new Set(pipeline?.done ?? []);
  const current = pipeline?.current ?? "";

  return (
    <div className="run-timeline" role="status" aria-label="Agent progress">
      {steps.map((step) => {
        const id = step.id as string;
        const status = id === current ? "running" : done.has(id) ? "done" : "todo";
        return (
          <span key={id} className={`run-step ${status}`}>
            <span className="run-step-dot" aria-hidden="true" />
            {step.label ?? id}
          </span>
        );
      })}
    </div>
  );
}
