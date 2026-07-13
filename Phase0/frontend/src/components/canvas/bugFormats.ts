export type BugReport = {
  title?: string;
  severity?: string;
  steps_to_reproduce?: string;
  expected_behavior?: string;
  actual_behavior?: string;
  environment?: string;
};

const FIELD_ORDER: { key: keyof BugReport; label: string }[] = [
  { key: "title", label: "Title" },
  { key: "severity", label: "Severity" },
  { key: "steps_to_reproduce", label: "Steps to reproduce" },
  { key: "expected_behavior", label: "Expected behavior" },
  { key: "actual_behavior", label: "Actual behavior" },
  { key: "environment", label: "Environment" },
];

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function bugToJson(bug: BugReport): string {
  const ordered: Record<string, unknown> = {};
  for (const { key } of FIELD_ORDER) {
    ordered[key] = bug[key] ?? "";
  }
  return JSON.stringify(ordered, null, 2);
}

export function bugToMarkdown(bug: BugReport): string {
  return [
    `# ${bug.title ?? "Untitled bug"}`,
    "",
    `**Severity:** ${bug.severity ?? "unset"}`,
    "",
    "## Steps to reproduce",
    "",
    bug.steps_to_reproduce ?? "",
    "",
    "## Expected behavior",
    "",
    bug.expected_behavior ?? "",
    "",
    "## Actual behavior",
    "",
    bug.actual_behavior ?? "",
    "",
    "## Environment",
    "",
    bug.environment ?? "",
    "",
  ].join("\n");
}

export function bugToHtml(bug: BugReport): string {
  const rows = FIELD_ORDER.filter(({ key }) => key !== "title" && key !== "severity")
    .map(
      ({ key, label }) =>
        `  <section>\n    <h2>${label}</h2>\n    <p>${escapeHtml(bug[key]).replace(/\n/g, "<br>")}</p>\n  </section>`
    )
    .join("\n");
  return [
    "<article>",
    `  <h1>${escapeHtml(bug.title)}</h1>`,
    `  <p class="severity">Severity: <strong>${escapeHtml(bug.severity)}</strong></p>`,
    rows,
    "</article>",
  ].join("\n");
}
