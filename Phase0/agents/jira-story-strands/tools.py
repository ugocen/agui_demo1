"""Backend tools for the Jira Story Writer.

Two kinds live here, and the difference matters:

* **Card tools** (`show_*`) exist so the frontend can render a readable view of
  something the model decided. Their ARGUMENTS are the card payload; their
  return value is a short acknowledgement, because sending the payload back
  would pay for the same tokens twice.
* **`publish_jira_story`** is not a card tool. It is the deterministic half of
  the product: it renders the artifact from structured content and lints the
  rendered bytes, and it returns BOTH so the canvas can show the document and
  the model can repair what the linter caught.

`request_design_context` and `request_clarification` are deliberately NOT here.
They are frontend-owned client-proxy tools (CopilotKit sends their definitions in
``RunAgentInput.tools``); defining a backend tool of the same name would silently
win the registry collision and the user would never see a card.
"""

from strands import tool

from jira_lint import lint_document
from jira_render import render_document

# The pipeline as the UI shows it: stable ids, human labels, fixed order.
PIPELINE_STEPS: list[dict[str, str]] = [
    {"id": "intake", "label": "Intake"},
    {"id": "design_context", "label": "Screen facts"},
    {"id": "criteria", "label": "Story & criteria"},
    {"id": "completeness", "label": "Completeness"},
    {"id": "publish", "label": "Artifact"},
    {"id": "scorecard", "label": "Checklist"},
    {"id": "report", "label": "Report"},
]

# Which step each tool call marks as reached.
TOOL_STEPS: dict[str, str] = {
    "show_intake_summary": "intake",
    "show_design_context": "design_context",
    "show_story_and_criteria": "criteria",
    "show_completeness_findings": "completeness",
    "publish_jira_story": "publish",
    "show_checklist_scorecard": "scorecard",
    "show_story_report": "report",
}

VALID_SEVERITY = {"PASS", "FAIL"}


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _text_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, (list, tuple)):
        return [str(value).strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _dict_list(value: object) -> list[dict]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, dict)]


# ---- card tools -----------------------------------------------------------


@tool
def show_intake_summary(
    persona: str,
    goal: str,
    benefit: str,
    problem_statement: str,
    targets_a_screen: bool,
    user_supplied_ac_count: int = 0,
    backend_notes: list[str] = None,
    frontend_notes: list[str] = None,
    infra_notes: list[str] = None,
    transcription_flags: list = None,
) -> dict:
    """Show what you understood from the user's input, before committing to criteria.

    Call this exactly once, first, on a new story.

    Args:
        persona: Who the story is for. "User" only when it is genuinely generic.
        goal: What they want to do.
        benefit: Why it matters — the business value.
        problem_statement: The problem being solved, in prose.
        targets_a_screen: True when the story concerns a UI screen (page, modal, list, form, tab).
        user_supplied_ac_count: How many acceptance criteria the user provided verbatim.
        backend_notes: Non-observable backend work the user mentioned.
        frontend_notes: Non-observable frontend work the user mentioned.
        infra_notes: Non-observable infrastructure work the user mentioned.
        transcription_flags: Objects with keys token, guess, why — for each token that
            looks mis-heard, ambiguous or self-contradictory. Do not resolve them here.
    """
    flags = [
        {
            "token": _text(flag.get("token")),
            "guess": _text(flag.get("guess")),
            "why": _text(flag.get("why")),
        }
        for flag in _dict_list(transcription_flags)
    ]
    return {"ok": True, "flags": len(flags), "targets_a_screen": bool(targets_a_screen)}


@tool
def show_design_context(
    screen_name: str = "",
    fields_and_controls: list[str] = None,
    visible_states: list[str] = None,
    visible_messages: list[str] = None,
    lists_or_tables: list[str] = None,
    roles_or_modes: list[str] = None,
    uncertain: list[str] = None,
) -> dict:
    """Report what you can actually SEE in the attached screenshot(s). Visible facts only.

    Call this once after screenshots arrive. Everything you list here becomes
    provided information you may ground criteria in, so it must be visible — not
    inferred.

    Args:
        screen_name: The screen's name, if it is visible.
        fields_and_controls: Buttons, inputs, dropdowns, tabs, menus, links, with visible labels.
        visible_states: Empty, loading, error or populated states, as shown.
        visible_messages: Exact on-screen text, verbatim — validation messages, banners, tooltips, modal text.
        lists_or_tables: One string per list or table, naming its columns and any
            visible sort or filter controls inline — "Results table: Name, Status,
            Created; sortable by Created". Never an object; the card shows a line.
        roles_or_modes: Role-specific or mode-specific controls that are visible.
        uncertain: Anything ambiguous — noted, never guessed.
    """
    return {
        "ok": True,
        "messages_read": len(_text_list(visible_messages)),
        "uncertain": len(_text_list(uncertain)),
    }


@tool
def show_story_and_criteria(
    persona: str,
    goal: str,
    benefit: str,
    coverage: str,
    acceptance_criteria: list,
) -> dict:
    """Show the user story and the acceptance criteria as a readable list.

    Write every clause as plain prose with NO keywords and NO asterisks — the
    renderer adds `*GIVEN* that`, `*WHEN*`, `*THEN*`, `*AND*` and `*BUT*`.

    Args:
        persona: The story's persona.
        goal: The goal clause.
        benefit: The value clause.
        coverage: "complete" when every criterion maps to the story, otherwise a
            one-line note naming the criterion that does not.
        acceptance_criteria: Objects with keys title (string), given (list of strings),
            when (list of strings), then (list of strings), but (list of strings,
            optional), source ("user" or "generated"), status ("draft", "validated"
            or "needs_fix").
    """
    shaped = []
    for index, item in enumerate(_dict_list(acceptance_criteria), start=1):
        source = _text(item.get("source")).lower()
        shaped.append(
            {
                "ac_id": f"AC {index}",
                "title": _text(item.get("title")) or f"Criterion {index}",
                "given": _text_list(item.get("given")),
                "when": _text_list(item.get("when")),
                "then": _text_list(item.get("then")),
                "but": _text_list(item.get("but")),
                "source": source if source in ("user", "generated") else "generated",
                "status": _text(item.get("status")) or "draft",
            }
        )
    if not shaped:
        raise ValueError("acceptance_criteria must contain at least one criterion")
    return {"ok": True, "criteria": len(shaped)}


@tool
def show_completeness_findings(findings: list) -> dict:
    """Show the six-category boundary analysis: what a default resolved, what needs a decision.

    Args:
        findings: Objects with keys ac_id (e.g. "AC 2", or "STORY" for a
            story-level gap), category (integer 1-6), gap (what is unanswered),
            is_mechanical (true when a documented default clearly resolves it),
            resolution (the default or screen fact you applied, when mechanical).
    """
    shaped = []
    for item in _dict_list(findings):
        try:
            category = int(item.get("category", 0))
        except (TypeError, ValueError):
            category = 0
        shaped.append(
            {
                "ac_id": _text(item.get("ac_id")) or "STORY",
                "category": category if 1 <= category <= 6 else 0,
                "gap": _text(item.get("gap")),
                "is_mechanical": bool(item.get("is_mechanical")),
                "resolution": _text(item.get("resolution")),
            }
        )
    resolved = sum(1 for entry in shaped if entry["is_mechanical"])
    return {"ok": True, "findings": len(shaped), "resolved": resolved, "escalated": len(shaped) - resolved}


@tool
def show_checklist_scorecard(items: list, loop: int = 0) -> dict:
    """Show your PASS/FAIL grading of the SEMANTIC checklist items.

    Grade only the items listed under SEMANTIC CHECKLIST. The format items are
    settled by publish_jira_story against the rendered bytes — never re-grade or
    contradict them.

    Args:
        items: Objects with keys item_id (integer), status ("PASS" or "FAIL"),
            reason (one line; required when the status is FAIL).
        loop: How many repair loops have run so far. 0 on the first pass.
    """
    shaped = []
    for item in _dict_list(items):
        try:
            item_id = int(item.get("item_id", 0))
        except (TypeError, ValueError):
            continue
        status = _text(item.get("status")).upper()
        shaped.append(
            {
                "item_id": item_id,
                "status": status if status in VALID_SEVERITY else "FAIL",
                "reason": _text(item.get("reason")),
            }
        )
    failed = sum(1 for entry in shaped if entry["status"] == "FAIL")
    return {"ok": True, "graded": len(shaped), "failed": failed, "loop": int(loop or 0)}


@tool
def show_story_report(
    changes_made: list[str] = None,
    open_business_decisions: list = None,
    recommendations: list[str] = None,
) -> dict:
    """Show PART 2 — the commentary that must never appear inside the artifact.

    Call this last.

    Args:
        changes_made: Every modification to the user's content, every standardized
            default applied (name the row), every fact read from a screenshot.
        open_business_decisions: Objects with keys question, recommended_default,
            context, blocking (boolean).
        recommendations: Anything worth saying that is not a change or a decision.
    """
    decisions = [
        {
            "question": _text(item.get("question")),
            "recommended_default": _text(item.get("recommended_default")),
            "context": _text(item.get("context")),
            "blocking": bool(item.get("blocking")),
        }
        for item in _dict_list(open_business_decisions)
    ]
    return {
        "ok": True,
        "changes": len(_text_list(changes_made)),
        "decisions": len(decisions),
    }


# ---- the deterministic one ------------------------------------------------


@tool
def publish_jira_story(
    title: str,
    persona: str,
    goal: str,
    benefit: str,
    acceptance_criteria: list,
    problem_statement: str = "",
    version: str = "1.0",
    backend_notes: list = None,
    frontend_notes: list = None,
    infra_notes: list = None,
    additional_notes: list = None,
    non_functional_requirements: list = None,
    out_of_scope: list = None,
) -> dict:
    """Render the Jira artifact onto the canvas and run the deterministic format checks.

    This tool — not you — owns every character of the markup. Send structured
    content in plain prose: no asterisks, no `h1.`/`h2.`/`h3.`, no `----`, no
    table pipes, no Markdown. Acceptance criteria clauses carry NO GWT keywords;
    the renderer adds them, indents the AND/BUT lines, and numbers the criteria
    flatly in the order you pass them.

    Returns the rendered document and a checklist verdict. If any check FAILED,
    fix the cause and call this again (at most twice) — the checks read the
    rendered bytes and are not negotiable.

    Args:
        title: The story title, without the h1 marker.
        persona: Who the story is for.
        goal: The goal clause, without the "I want to" prefix.
        benefit: The value clause, without the "So that" prefix.
        acceptance_criteria: Objects with keys title, given, when, then, but —
            each clause list holding plain prose strings in order. The first entry
            of a list is its keyword line; the rest become indented AND lines.
        problem_statement: The problem, in prose.
        version: Document version, e.g. "1.0", or "1.1" after a revision.
        backend_notes: Non-observable backend work. Omit when the user gave none.
        frontend_notes: Non-observable frontend work. Omit when the user gave none.
        infra_notes: Non-observable infrastructure work. Omit when the user gave none.
        additional_notes: Anything else that belongs in the description.
        non_functional_requirements: Objects with keys requirement and metric.
        out_of_scope: Items explicitly out of scope.
    """
    criteria = _dict_list(acceptance_criteria)
    if not criteria:
        raise ValueError("acceptance_criteria must contain at least one criterion")

    document = render_document(
        title=title,
        version=version,
        persona=persona,
        goal=goal,
        benefit=benefit,
        problem_statement=problem_statement,
        backend_notes=backend_notes,
        frontend_notes=frontend_notes,
        infra_notes=infra_notes,
        additional_notes=additional_notes,
        nfrs=non_functional_requirements,
        out_of_scope=out_of_scope,
        acceptance_criteria=criteria,
    )
    checks = lint_document(document)
    return {
        "document": document,
        "title": _text(title) or "Untitled Story",
        "version": _text(version) or "1.0",
        "filename": _filename(title, version),
        "format_checks": checks["items"],
        "failed": checks["failed"],
        "review": checks["review"],
        "summary": f"{checks['passed']}/{checks['total']} format checks passed",
    }


def _filename(title: str, version: str) -> str:
    """A safe .txt filename for the canvas download."""
    slug = "".join(char if char.isalnum() else "-" for char in _text(title).lower())
    slug = "-".join(part for part in slug.split("-") if part) or "jira-story"
    return f"{slug[:60]}-v{_text(version) or '1.0'}.txt"


ALL_TOOLS = [
    show_intake_summary,
    show_design_context,
    show_story_and_criteria,
    show_completeness_findings,
    show_checklist_scorecard,
    show_story_report,
    publish_jira_story,
]
