"use client";

/**
 * Keeps the conversation well-formed when the user CHATS instead of answering a
 * pending HITL card.
 *
 * The problem this solves, end to end:
 *
 * A client-proxy HITL tool (`useHumanInTheLoop`) pauses the run — CopilotKit
 * parks a promise and only writes the `role: "tool"` result message once the
 * user clicks. Meanwhile `agent.isRunning` is already `false`, so nothing stops
 * the composer. Typing feedback instead of clicking therefore ships a history
 * whose assistant `tool_calls` entry has NO matching tool result, followed by
 * the new user message. Bedrock rejects exactly that:
 *
 *     ValidationException: `tool_use` ids were found without `tool_result`
 *     blocks immediately after: <id>. Each `tool_use` block must have a
 *     corresponding `tool_result` block in the next message.
 *
 * and — this is why it looked like nothing happened at all — `ag_ui_strands`
 * receives that failure from Strands as an event carrying `force_stop` and
 * treats it like a normal completion (`agent.py`: `if event.get("complete") or
 * event.get("force_stop"): break`). `force_stop_reason` is dropped, the stream
 * ends with a clean `RUN_FINISHED`, and the wire shows a successful, EMPTY run:
 * `RUN_STARTED, STATE_SNAPSHOT, STATE_SNAPSHOT, RUN_FINISHED`. There is no
 * RUN_ERROR for the frontend to render, so the user's message just sat there.
 *
 * The repair: answer the open tool call with a neutral sentinel BEFORE the user
 * message goes out. Position matters as much as presence — Bedrock wants the
 * result in the *next* message, and appending it after the user's text fails
 * just as hard ("The number of toolResult blocks at messages.N.content exceeds
 * the number of toolUse blocks of previous turn"). Calling CopilotKit's own
 * `respond()` gets the position right for free: it splices the tool message at
 * `assistantIndex + 1`, and its follow-up run then carries
 * `[… assistant(tool_call), tool(sentinel), user(feedback)]` — verified working
 * against the live AgentCore runtime.
 *
 * Answering also flips the card to `status: "complete"`, so it visibly locks and
 * cannot be submitted a second time (which would put two results on one call and
 * break the history the other way).
 *
 * CopilotKit does the same repair for the *interrupt* protocol
 * (`use-interrupt.tsx` writes a tool message for every resolved interrupt, with
 * a comment about dangling tool calls) but has no equivalent for
 * `useHumanInTheLoop`, and no abandon path at all.
 *
 * Nothing here knows any agent id or tool name (AGENTS.md invariant 5): cards
 * register whatever `respond` they were handed, and the composer drains the
 * registry.
 */

import { CopilotChatInput, useAgent } from "@copilotkit/react-core/v2";
import type { CopilotChatInputProps } from "@copilotkit/react-core/v2";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef } from "react";

type Respond = (value: unknown) => void;

/**
 * What an unanswered card resolves to. It is read by an LLM, not by code, so it
 * says what happened in plain language and points at the message that follows —
 * the agents' own prompts already describe "submits it, or gives feedback in
 * chat" as the two normal paths, and this keeps the second one working.
 */
export const HITL_DISMISSED = {
  status: "dismissed",
  reason:
    "The user did not answer this request and replied in the chat instead. " +
    "Their message follows — treat it as the response and continue.",
};

type PendingHitlApi = {
  /** Register a live `respond`; returns the deregister for effect cleanup. */
  register: (toolCallId: string, respond: Respond) => () => void;
  /** Answer every open card with `value`. Returns how many were answered. */
  resolveAll: (value: unknown) => number;
  hasPending: () => boolean;
};

const PendingHitlContext = createContext<PendingHitlApi | null>(null);

export function PendingHitlProvider({ children }: { children: React.ReactNode }) {
  // A ref, not state: the set changes while a card is on screen but no one needs
  // to re-render because of it — the composer reads it once, on submit.
  const pending = useRef(new Map<string, Respond>());

  const register = useCallback((toolCallId: string, respond: Respond) => {
    pending.current.set(toolCallId, respond);
    return () => {
      pending.current.delete(toolCallId);
    };
  }, []);

  const resolveAll = useCallback((value: unknown) => {
    // Snapshot and clear first: `respond` resolves a promise that synchronously
    // walks CopilotKit's tool pipeline, so re-entering this map mid-iteration is
    // avoidable work at best and a double answer at worst.
    const responders = [...pending.current.values()];
    pending.current.clear();
    for (const respond of responders) respond(value);
    return responders.length;
  }, []);

  const hasPending = useCallback(() => pending.current.size > 0, []);

  const api = useMemo(
    () => ({ register, resolveAll, hasPending }),
    [register, resolveAll, hasPending]
  );
  return <PendingHitlContext.Provider value={api}>{children}</PendingHitlContext.Provider>;
}

/**
 * Publishes one card's `respond` while it is awaiting an answer.
 *
 * Rendered by every HITL card next to its UI. `respond` is only defined in the
 * `executing` branch of CopilotKit's status union, which is exactly the window
 * in which the run is paused — so the presence of `respond` IS the "pending"
 * signal and no status string has to be matched here.
 */
export function PendingHitlResponder({
  toolCallId,
  respond,
}: {
  toolCallId: string;
  respond?: Respond;
}) {
  const api = useContext(PendingHitlContext);
  useEffect(() => {
    if (!api || !respond) return;
    return api.register(toolCallId, respond);
  }, [api, toolCallId, respond]);
  return null;
}

/**
 * Builds the chat composer for one agent.
 *
 * `CopilotChat` ignores a top-level `onSubmitMessage` (it overwrites the prop
 * with its own handler when it assembles the view), so the interception has to
 * happen in the `input` SLOT, which is rendered with the real handler in its
 * props and can delegate to it.
 *
 * Call this from a `useMemo` keyed on the agent id: the return value is a
 * component type, and a fresh one on every render would remount the input and
 * drop what the user has typed.
 */
export function createHitlAwareInput(agentId: string): typeof CopilotChatInput {
  function HitlAwareInput(props: CopilotChatInputProps) {
    const api = useContext(PendingHitlContext);
    const { agent } = useAgent({ agentId });
    const { onSubmitMessage } = props;

    const submit = useCallback(
      (value: string) => {
        // Nothing open, or nothing to add it to: behave exactly as before.
        if (!api || !agent || !api.hasPending()) {
          onSubmitMessage?.(value);
          return;
        }
        // Order is the whole fix. Append the user's message FIRST so that the
        // tool result `respond()` splices in lands between the tool call and the
        // message, then let the follow-up run that `respond()` triggers carry
        // both. Submitting normally as well would send the message twice.
        agent.addMessage({ id: crypto.randomUUID(), role: "user", content: value });
        api.resolveAll(HITL_DISMISSED);
      },
      [api, agent, onSubmitMessage]
    );

    return <CopilotChatInput {...props} onSubmitMessage={submit} />;
  }
  // The `input` slot's type is `typeof CopilotChatInput` — the concrete class
  // with its static sub-components (`.SendButton`, …) — but `renderSlot` only
  // ever does `createElement(slot, props)` and never reads those statics off a
  // component slot, so a plain function component is correct at runtime. The
  // cast records that; attaching the statics would be dead ceremony.
  return HitlAwareInput as unknown as typeof CopilotChatInput;
}
