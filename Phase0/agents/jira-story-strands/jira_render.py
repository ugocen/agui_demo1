"""Deterministic renderer — structured story in, raw Jira markup out.

Layout is owned HERE, in code, and nowhere else. The model decides *content*
(which persona, which acceptance criteria, what the boundary behavior is); this
module decides every character of *form*: section order, heading levels, the
bold single-asterisk keywords, the exact two-space AND/BUT indent, the table
pipes, where the ``----`` rules go and — just as importantly — where they do
not (never between ACs).

That split is the whole reason the artifact is reproducible. A model asked to
"emit Jira markup" drifts: it will indent three spaces on a long run, promote a
`h3.` to `h2.`, or slip in a Markdown `**bold**`. Those are not judgment calls,
so they are not the model's to make.

The output is raw text, ready to paste into Jira. Never markdown, never HTML.
"""

from datetime import datetime, timezone

# Every section that may appear, in the ONE order the spec allows. `jira_lint`
# checks a rendered document against this same list, so order can only be wrong
# in one place if it is wrong in both.
SECTION_ORDER: list[str] = [
    "title",
    "version",
    "user_story",
    "problem_statement",
    "backend_notes",
    "frontend_notes",
    "infra_notes",
    "additional_notes",
    "nfrs",
    "out_of_scope",
    "acceptance_criteria",
]

_AND = "  *AND* "
_BUT = "  *BUT* "


def _clean(value: object) -> str:
    """Collapse a value to a single trimmed line-preserving string."""
    if value is None:
        return ""
    return str(value).strip()


def _lines(values: object) -> list[str]:
    """Normalize a list-ish field to a list of non-empty strings."""
    if values is None:
        return []
    if isinstance(values, str):
        text = values.strip()
        return [text] if text else []
    if not isinstance(values, (list, tuple)):
        return [str(values).strip()]
    return [str(item).strip() for item in values if str(item).strip()]


def _strip_keyword(text: str) -> str:
    """Remove a GWT keyword the model prefixed to a clause it was asked to leave bare.

    The prompt is explicit that clauses arrive as plain prose and the renderer
    adds the keywords. Models comply most of the time; the failure when they do
    not is `*GIVEN* that *GIVEN* that the user…`, which then fails checklist
    items 8 and 9 for a reason that has nothing to do with the content. Stripping
    here costs one pass and makes the artifact correct either way.
    """
    stripped = text.strip()
    for keyword in ("GIVEN", "WHEN", "THEN", "AND", "BUT"):
        for form in (f"*{keyword}*", f"**{keyword}**", keyword):
            if stripped.upper().startswith(form.upper()):
                remainder = stripped[len(form) :].lstrip(" :,")
                # Only treat it as a keyword when something follows it —
                # otherwise a clause that legitimately begins with the word
                # "and" would be eaten down to nothing.
                if remainder:
                    return remainder
    return stripped


def _clauses(values: object) -> list[str]:
    """Clause list with any model-supplied GWT keyword removed."""
    return [cleaned for item in _lines(values) if (cleaned := _strip_keyword(item))]


def _strip_leading_that(text: str) -> str:
    """Drop a leading "that" so the renderer can always emit ``*GIVEN* that``.

    Checklist item 8 wants a lowercase "that" immediately after the keyword. If
    the model already wrote one ("that the user is signed in") a naive template
    produces "*GIVEN* that that the user…", so the word is removed here and
    re-added by the caller — the keyword line then reads correctly whether or
    not the model included it.
    """
    lowered = text.lstrip()
    for prefix in ("that ", "That ", "THAT "):
        if lowered.startswith(prefix):
            return lowered[len(prefix) :].lstrip()
    return lowered


def render_acceptance_criterion(index: int, criterion: dict) -> list[str]:
    """One AC block. Numbering is the caller's ``index``, never the model's.

    Flat numbering is a spec rule (AC 1, AC 2 — never AC 1.1) and renumbering on
    insert is another. Both hold for free when the sequence is generated from
    the list position instead of read off a model-supplied id.
    """
    title = _clean(criterion.get("title")) or "Untitled"
    out: list[str] = [f"h3. *AC {index}- {title}*", ""]

    given = _clauses(criterion.get("given"))
    when = _clauses(criterion.get("when"))
    then = _clauses(criterion.get("then"))
    but = _clauses(criterion.get("but"))

    if given:
        out.append(f"*GIVEN* that {_strip_leading_that(given[0])}")
        out.extend(f"{_AND}{item}" for item in given[1:])
    if when:
        out.append(f"*WHEN* {when[0]}")
        out.extend(f"{_AND}{item}" for item in when[1:])
    if then:
        out.append(f"*THEN* {then[0]}")
        out.extend(f"{_AND}{item}" for item in then[1:])
    # BUT closes the THEN block — it is an exception to the outcome, so it is
    # indented like AND and never starts its own keyword line.
    out.extend(f"{_BUT}{item}" for item in but)
    return out


def render_document(
    *,
    title: str,
    version: str = "1.0",
    last_updated: str = "",
    persona: str = "",
    goal: str = "",
    benefit: str = "",
    problem_statement: str = "",
    backend_notes: object = None,
    frontend_notes: object = None,
    infra_notes: object = None,
    additional_notes: object = None,
    nfrs: object = None,
    out_of_scope: object = None,
    acceptance_criteria: object = None,
) -> str:
    """Assemble the full artifact. Optional sections are omitted when empty.

    "Include a section only when the user provided relevant content" is a spec
    rule, so an empty list means the heading does not appear at all — not that
    it appears with a placeholder under it.
    """
    # A date is metadata the container can observe, not information about the
    # product, so filling it is not "inventing". The model has no clock.
    stamp = _clean(last_updated) or datetime.now(timezone.utc).date().isoformat()

    out: list[str] = [
        f"h1. {_clean(title) or 'Untitled Story'}",
        "",
        f"_Document Version: {_clean(version) or '1.0'}_",
        f"_Last Updated: {stamp}_",
        "",
        "----",
        "",
        "h2. User Story",
        "",
        f"*As* a {_clean(persona) or 'User'},",
        f"*I want to* {_clean(goal)}",
        f"*So that* {_clean(benefit)}",
    ]

    if _clean(problem_statement):
        out += ["", "*Problem Statement:*", _clean(problem_statement)]

    for label, values in (
        ("*Backend Tasks or Notes:*", backend_notes),
        ("*Frontend Tasks or Notes:*", frontend_notes),
        ("*Infrastructure Tasks or Notes:*", infra_notes),
        ("*Additional Notes*", additional_notes),
    ):
        items = _lines(values)
        if items:
            out += ["", label] + [f"- {item}" for item in items]

    rows = [row for row in (nfrs or []) if isinstance(row, dict)]
    if rows:
        out += ["", "*Non-Functional Requirements*", "", "||Requirement||Metric||"]
        out += [
            f"|{_clean(row.get('requirement'))}|{_clean(row.get('metric'))}|" for row in rows
        ]

    scope = _lines(out_of_scope)
    if scope:
        out += ["", "*Out of Scope*", ""] + [f"- {item}" for item in scope]

    criteria = [item for item in (acceptance_criteria or []) if isinstance(item, dict)]
    out += ["", "----", "", "h2. Acceptance Criteria", ""]
    for position, criterion in enumerate(criteria, start=1):
        out += render_acceptance_criterion(position, criterion)
        # A single blank line separates ACs. Never a `----` rule — that is
        # checklist item 12, and it is the most common thing a model gets wrong.
        out.append("")

    # One trailing newline, no trailing blank lines: the artifact is pasted, so
    # stray whitespace at the end shows up as empty paragraphs in Jira.
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"
