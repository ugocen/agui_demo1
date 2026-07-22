"use client";

/**
 * Human-in-the-loop (HITL) tools — client-proxy tools the AGENTS call and then
 * PAUSE on until the browser responds.
 *
 * These tools are owned by the frontend: CopilotKit sends each definition to the
 * agent in `RunAgentInput.tools`, `ag-ui-strands` / `ag-ui-langgraph` register it
 * as a client-proxy tool, the agent calls it by name, the run pauses, and
 * `respond(value)` resumes the agent with the user's decision. Mount
 * `<HumanInTheLoop />` inside `<CopilotKitProvider>` (next to `<FallbackRender />`).
 *
 * Schemas are built with `zod/v3` — same as `richCatalog` — because CopilotKit's
 * v2 schema extraction reads zod v3 internals (the reference AgentCore example
 * uses zod v3 too).
 *
 * The `request_ticket_approval` and `request_go_nogo` payload/response contracts
 * match the G0 HITL cards. The form/choice tools (`draft_bug_report`,
 * `ask_choice`, `draft_press_release`) follow their agents' docstrings.
 */

import { useHumanInTheLoop, useInterrupt } from "@copilotkit/react-core/v2";
import { useEffect, useRef, useState } from "react";
import { z } from "zod/v3";

import { DocumentField, useDocumentCanvas } from "@/components/canvas/DocumentCanvas";
import { PendingHitlResponder } from "@/components/hitl/pendingHitl";

type Respond = (value: unknown) => void;
const isDone = (status: string) => status === "complete";

// Every client-proxy card publishes its `respond` while the run is paused on it,
// so that typing in the chat can answer the card instead of leaving a dangling
// tool call — see components/hitl/pendingHitl.tsx for what that fixes. It is one
// line per registration rather than something the cards do for themselves,
// because the tools are registered here and the cards stay presentational.
function hitl(toolCallId: string, respond: Respond | undefined, card: React.ReactNode) {
  return (
    <>
      <PendingHitlResponder toolCallId={toolCallId} respond={respond} />
      {card}
    </>
  );
}

// ---- shared styles (inline, consistent with the app's lightweight cards) ----
const box: React.CSSProperties = {
  border: "1px solid var(--border, #e2e2e2)",
  borderRadius: 8,
  padding: 12,
  margin: "6px 0",
  fontSize: 14,
  background: "var(--card-bg, #fafafa)",
};
const row: React.CSSProperties = { display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" };
const btn: React.CSSProperties = {
  padding: "6px 12px",
  borderRadius: 6,
  border: "1px solid var(--border, #ccc)",
  cursor: "pointer",
};
const field: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  padding: 6,
  marginTop: 4,
  borderRadius: 6,
  border: "1px solid var(--border, #ccc)",
  fontSize: 13,
};

function Note({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled: boolean }) {
  return (
    <input
      style={field}
      placeholder="Optional note…"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

// 1) request_ticket_approval (SDLC Planner) → { decision: "approved"|"rejected", note? }
function ApprovalCard({
  status,
  respond,
  args,
}: {
  status: string;
  respond?: Respond;
  args: { summary?: string; tickets?: { title?: string; points?: number }[] };
}) {
  const [note, setNote] = useState("");
  const done = isDone(status);
  return (
    <div style={box}>
      <strong>Ticket approval</strong>
      <div style={{ marginTop: 4 }}>{args.summary}</div>
      <ul style={{ margin: "6px 0", paddingLeft: 18 }}>
        {(args.tickets ?? []).map((t, i) => (
          <li key={i}>
            {t.title} {t.points != null ? `(${t.points} pts)` : ""}
          </li>
        ))}
      </ul>
      <Note value={note} onChange={setNote} disabled={done} />
      <div style={row}>
        <button style={btn} disabled={done || !respond} onClick={() => respond?.({ decision: "approved", note })}>
          Approve
        </button>
        <button style={btn} disabled={done || !respond} onClick={() => respond?.({ decision: "rejected", note })}>
          Reject
        </button>
      </div>
    </div>
  );
}

/**
 * Read a LangGraph interrupt's payload, which arrives JSON-ENCODED AS A STRING.
 *
 * `ag-ui-langgraph` emits the interrupt as a CUSTOM `on_interrupt` event whose
 * `value` is a string, while the same payload sits decoded under `rawEvent.value`:
 *
 *   {"type":"CUSTOM","name":"on_interrupt",
 *    "rawEvent":{"value":{"tool":"request_go_nogo","recommendation":"no-go",...}},
 *    "value":"{\"tool\": \"request_go_nogo\", \"recommendation\": \"no-go\", ...}"}
 *
 * This used to be `event.value as {...}`, which is a compile-time cast over a
 * runtime string: every field read came back `undefined`, so the card rendered
 * with a blank recommendation and no reasons — while the agent had sent both.
 * `scripts/smoke_test.py` decodes the same string and therefore stayed green.
 *
 * Objects are still accepted, so this keeps working if the event shape changes.
 */
function interruptValue<T extends object>(raw: unknown): Partial<T> {
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw) as Partial<T>;
    } catch {
      return {};
    }
  }
  return (raw ?? {}) as Partial<T>;
}

// 2) request_go_nogo (Release Readiness) → { decision: "go"|"no-go", note? }
// Release go/no-go arrives as a LangGraph interrupt() (not a client-proxy tool),
// so it has no `status`/`respond` — it uses `resolve` and tracks its own done state.
function GoNoGoInterrupt({
  recommendation,
  reasons,
  resolve,
}: {
  recommendation?: string;
  reasons?: string[];
  resolve: Respond;
}) {
  const [note, setNote] = useState("");
  const [done, setDone] = useState(false);
  const decide = (decision: "go" | "no-go") => {
    if (done) return;
    setDone(true);
    resolve({ decision, note });
  };
  return (
    <div style={box}>
      <strong>Go / No-Go</strong>
      <div style={{ marginTop: 4 }}>
        Recommendation: <b>{recommendation}</b>
      </div>
      <ul style={{ margin: "6px 0", paddingLeft: 18 }}>
        {(reasons ?? []).map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ul>
      <Note value={note} onChange={setNote} disabled={done} />
      <div style={row}>
        <button style={btn} disabled={done} onClick={() => decide("go")}>
          Go
        </button>
        <button style={btn} disabled={done} onClick={() => decide("no-go")}>
          No-Go
        </button>
      </div>
    </div>
  );
}

// 4) ask_choice (Press Release) → { choice }
function ChoiceCard({
  status,
  respond,
  args,
}: {
  status: string;
  respond?: Respond;
  args: { question?: string; options?: string[] };
}) {
  const done = isDone(status);
  return (
    <div style={box}>
      <strong>{args.question}</strong>
      <div style={row}>
        {(args.options ?? []).map((opt, i) => (
          <button key={i} style={btn} disabled={done || !respond} onClick={() => respond?.({ choice: opt })}>
            {opt}
          </button>
        ))}
      </div>
    </div>
  );
}

// Generic editable form for the "draft_*" tools: pre-fill from args, submit edits.
//
// `args` ARRIVES EMPTY AND FILLS IN OVER TIME. CopilotKit renders the card as soon
// as TOOL_CALL_START lands, then the agent streams the arguments in as
// TOOL_CALL_ARGS deltas (literally a few characters per event). So the first
// render sees `{}`.
//
// This used to seed the fields with `useState(() => ...args...)`, whose initializer
// runs ONCE — on that first, empty render. The values then never caught up, and
// every draft form rendered permanently blank while the agent had sent a full
// press release. The two cards that read `args` directly in render
// (ApprovalCard, ChoiceCard) were fine, which is what made this look agent-specific.
//
// So: mirror `args` into state as it streams, but never clobber a field the user
// has already typed in.
function EditableForm({
  title,
  toolCallId,
  status,
  respond,
  args,
  fields,
}: {
  title: string;
  toolCallId: string;
  status: string;
  respond?: Respond;
  args: Record<string, unknown>;
  fields: DocumentField[];
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const edited = useRef<Set<string>>(new Set());
  const { publish } = useDocumentCanvas();
  // Depend on the serialized args: the object identity changes on every render,
  // so [args] would re-run this forever.
  const argsKey = JSON.stringify(args);
  useEffect(() => {
    setValues((prev) => {
      const next = { ...prev };
      for (const f of fields) {
        if (!edited.current.has(f.key)) next[f.key] = String(args[f.key] ?? "");
      }
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [argsKey]);

  // Mirror the form into the document canvas (components/canvas/DocumentCanvas):
  // the chat shows the draft as fields to edit, the side panel shows the same
  // draft as the document it will become, live as the agent streams it and as the
  // user types. Every draft_* tool gets this — nothing here is per-agent.
  const valuesKey = JSON.stringify(values);
  useEffect(() => {
    // Don't open the panel on an all-empty first render; wait for real content.
    if (!Object.values(values).some((value) => value.trim() !== "")) return;
    publish({ id: toolCallId, title, fields, values });
    // `fields` is a literal in the caller's render, so its identity changes every
    // render while its content is fixed per tool — depending on it would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toolCallId, title, valuesKey, publish]);

  const done = isDone(status);
  const set = (k: string, v: string) => {
    edited.current.add(k);
    setValues((prev) => ({ ...prev, [k]: v }));
  };
  return (
    <div style={box}>
      <strong>{title}</strong>
      {fields.map((f) => (
        <div key={f.key} style={{ marginTop: 8 }}>
          <label style={{ fontSize: 12, color: "#666" }}>{f.label}</label>
          {/* `?? ""` because `values` is empty on the first render (see above), and
              a value of `undefined` makes React treat the field as UNCONTROLLED —
              it then logs "changing an uncontrolled input to be controlled" as soon
              as the streamed args arrive. */}
          {f.multiline ? (
            <textarea style={{ ...field, minHeight: 64 }} value={values[f.key] ?? ""} disabled={done} onChange={(e) => set(f.key, e.target.value)} />
          ) : (
            <input style={field} value={values[f.key] ?? ""} disabled={done} onChange={(e) => set(f.key, e.target.value)} />
          )}
        </div>
      ))}
      <div style={row}>
        <button style={btn} disabled={done || !respond} onClick={() => respond?.(values)}>
          Submit
        </button>
      </div>
    </div>
  );
}

// 6) request_design_context (Jira Story) → { action: "attach" | "skip" }
//
// This card asks for screenshots but cannot RECEIVE them, and that is a protocol
// fact rather than a shortcut. An AG-UI `ToolMessage.content` is typed `str`, and
// the Strands adapter turns a tool result into exactly one `{"text": …}` block
// inside a `toolResult` — there is no image branch on that path. Base64 returned
// through `respond()` would reach the model as literal text: enormous, and not an
// image. Image bytes only ever reach the model as multimodal content on a USER
// message, so the working flow is to hand the turn back and let the user attach
// in the composer. The agent's prompt knows to stop and wait after "attach".
function DesignContextRequestCard({
  status,
  respond,
  args,
}: {
  status: string;
  respond?: Respond;
  args: { reason?: string };
}) {
  const done = isDone(status);
  return (
    <div style={box}>
      <strong>Screenshots would sharpen this</strong>
      <div style={{ marginTop: 4 }}>
        {args.reason ||
          "Seeing the screen shows the empty state, the exact message text, the columns and the role-specific controls — the details acceptance criteria are usually missing."}
      </div>
      <div style={{ marginTop: 8, fontSize: 13, color: "#666" }}>
        Attach the current screen and the expected design with the paperclip in the
        message box, then send. PNG, JPEG, GIF or WEBP.
      </div>
      <div style={row}>
        <button style={btn} disabled={done || !respond} onClick={() => respond?.({ action: "attach" })}>
          I&apos;ll attach them
        </button>
        <button style={btn} disabled={done || !respond} onClick={() => respond?.({ action: "skip" })}>
          Skip — use the defaults
        </button>
      </div>
    </div>
  );
}

type Flag = { token?: string; guess?: string; why?: string };
type Decision = { question?: string; recommended_default?: string; context?: string };

// 7) request_clarification (Jira Story) → { answers: Record<string, string> }
//
// Two kinds of question share one card because they share one shape: something
// the agent could not decide, plus its best suggestion. Transcription flags are
// tokens it thinks it mis-heard from dictation; business decisions are the ones
// no project default covers. Both arrive pre-filled with the suggestion, so the
// fast path is a single click on Continue.
function ClarificationCard({
  status,
  respond,
  args,
}: {
  status: string;
  respond?: Respond;
  args: { flags?: Flag[]; decisions?: Decision[] };
}) {
  const flags = args.flags ?? [];
  const decisions = args.decisions ?? [];
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const edited = useRef<Set<string>>(new Set());
  const done = isDone(status);

  // Same streaming-args discipline as EditableForm: the suggestions arrive after
  // the first render, so they are mirrored in an effect keyed on the serialized
  // args and never clobber something the user has already typed.
  const argsKey = JSON.stringify(args);
  useEffect(() => {
    setAnswers((prev) => {
      const next = { ...prev };
      for (const flag of flags) {
        const key = flag.token ?? "";
        if (key && !edited.current.has(key)) next[key] = flag.guess ?? "";
      }
      for (const decision of decisions) {
        const key = decision.question ?? "";
        if (key && !edited.current.has(key)) next[key] = decision.recommended_default ?? "";
      }
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [argsKey]);

  const set = (key: string, value: string) => {
    edited.current.add(key);
    setAnswers((prev) => ({ ...prev, [key]: value }));
  };

  if (flags.length === 0 && decisions.length === 0) {
    return <div style={box}>Preparing questions…</div>;
  }

  return (
    <div style={box}>
      <strong>A few things I could not decide</strong>
      {flags.map((flag, index) => (
        <div key={`flag-${flag.token ?? index}`} style={{ marginTop: 10 }}>
          <label style={{ fontSize: 12, color: "#666" }}>
            Heard <code>{flag.token}</code>
            {flag.why ? ` — ${flag.why}` : ""}
          </label>
          <input
            style={field}
            value={answers[flag.token ?? ""] ?? ""}
            disabled={done}
            onChange={(event) => set(flag.token ?? "", event.target.value)}
          />
        </div>
      ))}
      {decisions.map((decision, index) => (
        <div key={`decision-${decision.question ?? index}`} style={{ marginTop: 10 }}>
          <label style={{ fontSize: 12, color: "#666" }}>{decision.question}</label>
          {decision.context ? (
            <div style={{ fontSize: 12, color: "#888", marginTop: 2 }}>{decision.context}</div>
          ) : null}
          <input
            style={field}
            value={answers[decision.question ?? ""] ?? ""}
            disabled={done}
            onChange={(event) => set(decision.question ?? "", event.target.value)}
          />
        </div>
      ))}
      <div style={row}>
        <button style={btn} disabled={done || !respond} onClick={() => respond?.({ answers })}>
          Continue
        </button>
      </div>
    </div>
  );
}

/**
 * Registers every HITL client-proxy tool. Render inside <CopilotKitProvider>.
 */
export function HumanInTheLoop({ agentId }: { agentId: string }) {
  // 1) SDLC Planner — ticket creation approval
  useHumanInTheLoop({
    name: "request_ticket_approval",
    description: "Ask the user to approve or reject creating the proposed tickets.",
    parameters: z.object({
      summary: z.string().describe("One-line summary of what will be created"),
      tickets: z
        .array(z.object({ title: z.string(), points: z.number() }))
        .describe("The tickets that would be created"),
    }),
    render: (p) =>
      hitl(
        p.toolCallId,
        p.respond as Respond,
        <ApprovalCard status={p.status} respond={p.respond as Respond} args={p.args as ApprovalArgs} />
      ),
  });

  // 2) Release Readiness — go/no-go is a LangGraph interrupt(), NOT a Strands
  // client-proxy tool, so it surfaces via useInterrupt (not useHumanInTheLoop).
  // graph.py sends interrupt({tool, recommendation, reasons}) and reads {decision, note}.
  useInterrupt({
    agentId,
    render: ({ event, resolve }) => {
      const v = interruptValue<{
        tool?: string;
        recommendation?: string;
        reasons?: string[];
      }>(event?.value);
      if (v.tool && v.tool !== "request_go_nogo") return <></>;
      return (
        <GoNoGoInterrupt
          recommendation={v.recommendation}
          reasons={v.reasons}
          resolve={resolve as Respond}
        />
      );
    },
  });

  // 3) Bug Report — review/edit the proposed report, then submit
  useHumanInTheLoop({
    name: "draft_bug_report",
    description: "Show the proposed bug report for the user to edit and submit.",
    parameters: z.object({
      title: z.string(),
      severity: z.enum(["critical", "high", "medium", "low"]),
      steps_to_reproduce: z.string(),
      expected_behavior: z.string(),
      actual_behavior: z.string(),
      environment: z.string(),
    }),
    render: (p) =>
      hitl(
        p.toolCallId,
        p.respond as Respond,
        <EditableForm
          title="Bug report"
          toolCallId={p.toolCallId}
          status={p.status}
          respond={p.respond as Respond}
          args={p.args as Record<string, unknown>}
          fields={[
            { key: "title", label: "Title" },
            { key: "severity", label: "Severity" },
            { key: "steps_to_reproduce", label: "Steps to reproduce", multiline: true },
            { key: "expected_behavior", label: "Expected behavior", multiline: true },
            { key: "actual_behavior", label: "Actual behavior", multiline: true },
            { key: "environment", label: "Environment" },
          ]}
        />
      ),
  });

  // 4) Press Release — one multiple-choice framing question
  useHumanInTheLoop({
    name: "ask_choice",
    description: "Ask the user one multiple-choice framing question.",
    parameters: z.object({
      question: z.string(),
      options: z.array(z.string()).describe("2-4 options the user picks from"),
    }),
    render: (p) =>
      hitl(
        p.toolCallId,
        p.respond as Respond,
        <ChoiceCard status={p.status} respond={p.respond as Respond} args={p.args as ChoiceArgs} />
      ),
  });

  // 5) Press Release — review/edit the draft, then submit
  useHumanInTheLoop({
    name: "draft_press_release",
    description: "Show the proposed press release for the user to edit and submit.",
    parameters: z.object({
      headline: z.string(),
      subheadline: z.string(),
      dateline: z.string(),
      body: z.string(),
      boilerplate: z.string(),
      contact: z.string(),
    }),
    render: (p) =>
      hitl(
        p.toolCallId,
        p.respond as Respond,
        <EditableForm
          title="Press release"
          toolCallId={p.toolCallId}
          status={p.status}
          respond={p.respond as Respond}
          args={p.args as Record<string, unknown>}
          fields={[
            { key: "headline", label: "Headline" },
            { key: "subheadline", label: "Subheadline" },
            { key: "dateline", label: "Dateline" },
            { key: "body", label: "Body", multiline: true },
            { key: "boilerplate", label: "Boilerplate", multiline: true },
            { key: "contact", label: "Contact" },
          ]}
        />
      ),
  });

  // 6) Jira Story — ask for screenshots of the current screen and expected design
  useHumanInTheLoop({
    name: "request_design_context",
    description:
      "Ask the user to attach screenshots of the current screen and the expected design, or to skip. " +
      "Returns {action: 'attach'} — reply with one line asking them to attach and send, then STOP this turn; " +
      "the images arrive in their next message — or {action: 'skip'} to continue with the standardized defaults.",
    parameters: z.object({
      reason: z
        .string()
        .describe("One line on what seeing the screen would let you write more precisely"),
    }),
    render: (p) =>
      hitl(
        p.toolCallId,
        p.respond as Respond,
        <DesignContextRequestCard
          status={p.status}
          respond={p.respond as Respond}
          args={p.args as { reason?: string }}
        />
      ),
  });

  // 7) Jira Story — resolve mis-heard tokens and blocking business decisions
  useHumanInTheLoop({
    name: "request_clarification",
    description:
      "Ask the user to resolve mis-heard tokens and blocking business decisions. Each item carries your " +
      "suggestion, pre-filled. Returns {answers: {<token or question>: <the user's answer>}}. " +
      "Never ask about anything a standardized default already covers.",
    parameters: z.object({
      flags: z
        .array(
          z.object({
            token: z.string().describe("The token as you heard it — this is the answer key"),
            guess: z.string().describe("Your best reading, pre-filled for the user"),
            why: z.string().describe("Why it looks mis-heard or ambiguous"),
          })
        )
        .describe("Transcription flags. Empty array when there are none."),
      decisions: z
        .array(
          z.object({
            question: z
              .string()
              .describe("Answerable by a product owner in one sentence — this is the answer key"),
            recommended_default: z.string().describe("Your suggested answer, pre-filled"),
            context: z.string().describe("One line on why this matters"),
          })
        )
        .describe("Blocking business decisions. Empty array when there are none."),
    }),
    render: (p) =>
      hitl(
        p.toolCallId,
        p.respond as Respond,
        <ClarificationCard
          status={p.status}
          respond={p.respond as Respond}
          args={p.args as { flags?: Flag[]; decisions?: Decision[] }}
        />
      ),
  });

  return null;
}

type ApprovalArgs = { summary?: string; tickets?: { title?: string; points?: number }[] };
type ChoiceArgs = { question?: string; options?: string[] };
