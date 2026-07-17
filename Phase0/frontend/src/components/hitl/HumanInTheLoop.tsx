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
import { useState } from "react";
import { z } from "zod/v3";

type Respond = (value: unknown) => void;
const isDone = (status: string) => status === "complete";

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
function EditableForm({
  title,
  status,
  respond,
  args,
  fields,
}: {
  title: string;
  status: string;
  respond?: Respond;
  args: Record<string, unknown>;
  fields: { key: string; label: string; multiline?: boolean }[];
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.key, String(args[f.key] ?? "")]))
  );
  const done = isDone(status);
  const set = (k: string, v: string) => setValues((prev) => ({ ...prev, [k]: v }));
  return (
    <div style={box}>
      <strong>{title}</strong>
      {fields.map((f) => (
        <div key={f.key} style={{ marginTop: 8 }}>
          <label style={{ fontSize: 12, color: "#666" }}>{f.label}</label>
          {f.multiline ? (
            <textarea style={{ ...field, minHeight: 64 }} value={values[f.key]} disabled={done} onChange={(e) => set(f.key, e.target.value)} />
          ) : (
            <input style={field} value={values[f.key]} disabled={done} onChange={(e) => set(f.key, e.target.value)} />
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
    render: (p) => <ApprovalCard status={p.status} respond={p.respond as Respond} args={p.args as ApprovalArgs} />,
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
    render: (p) => (
      <EditableForm
        title="Bug report"
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
    render: (p) => <ChoiceCard status={p.status} respond={p.respond as Respond} args={p.args as ChoiceArgs} />,
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
    render: (p) => (
      <EditableForm
        title="Press release"
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

  return null;
}

type ApprovalArgs = { summary?: string; tickets?: { title?: string; points?: number }[] };
type ChoiceArgs = { question?: string; options?: string[] };
