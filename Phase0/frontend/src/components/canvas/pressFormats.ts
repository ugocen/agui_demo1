export type PressRelease = {
  headline?: string;
  subheadline?: string;
  dateline?: string;
  body?: string;
  boilerplate?: string;
  contact?: string;
};

const FIELD_ORDER: { key: keyof PressRelease; label: string }[] = [
  { key: "headline", label: "Headline" },
  { key: "subheadline", label: "Subheadline" },
  { key: "dateline", label: "Dateline" },
  { key: "body", label: "Body" },
  { key: "boilerplate", label: "Boilerplate" },
  { key: "contact", label: "Contact" },
];

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function pressToJson(press: PressRelease): string {
  const ordered: Record<string, unknown> = {};
  for (const { key } of FIELD_ORDER) {
    ordered[key] = press[key] ?? "";
  }
  return JSON.stringify(ordered, null, 2);
}

export function pressToMarkdown(press: PressRelease): string {
  return [
    "**FOR IMMEDIATE RELEASE**",
    "",
    `# ${press.headline ?? "Untitled release"}`,
    press.subheadline ? `### ${press.subheadline}` : "",
    "",
    `${press.dateline ?? ""} ${press.body ?? ""}`.trim(),
    "",
    "---",
    "",
    press.boilerplate ?? "",
    "",
    "**Media contact**",
    "",
    press.contact ?? "",
    "",
  ]
    .filter((line, index, all) => !(line === "" && all[index - 1] === ""))
    .join("\n");
}

export function pressToHtml(press: PressRelease): string {
  const paragraphs = (press.body ?? "")
    .split(/\n\s*\n/)
    .map((p) => `    <p>${escapeHtml(p).replace(/\n/g, "<br>")}</p>`)
    .join("\n");
  return [
    "<article>",
    '  <p class="release-tag">FOR IMMEDIATE RELEASE</p>',
    `  <h1>${escapeHtml(press.headline)}</h1>`,
    press.subheadline ? `  <h2>${escapeHtml(press.subheadline)}</h2>` : "",
    press.dateline ? `  <p class="dateline"><strong>${escapeHtml(press.dateline)}</strong></p>` : "",
    paragraphs,
    "  <hr>",
    `  <p class="boilerplate">${escapeHtml(press.boilerplate).replace(/\n/g, "<br>")}</p>`,
    "  <h3>Media contact</h3>",
    `  <p class="contact">${escapeHtml(press.contact).replace(/\n/g, "<br>")}</p>`,
    "</article>",
  ]
    .filter(Boolean)
    .join("\n");
}
