"""Standardized default resolutions — the project conventions from the spec.

These are DOCUMENTED PLATFORM CONVENTIONS, not invented information. When a
completeness gap is mechanical (an unstated empty state, an unstated sort
behavior), the agent resolves it from this table and reports the fill under
CHANGES MADE. Only genuine business decisions — the ones no convention covers —
are escalated to the user.

The table lives here, once, and is rendered into the system prompt by
``prompts.py``. Keeping it as data rather than prose in the prompt is what lets
the report name the exact row it applied ("Search default applied") instead of
paraphrasing it differently every run.
"""

# concern -> the project's standing resolution for it
PROJECT_DEFAULTS: dict[str, str] = {
    "Search": (
        "Matches across all relevant columns or fields, partial substring, "
        "case-insensitive. State explicitly any excluded field, and that no match "
        "shows an empty result. For grouped lists, state whether group headings "
        "are searched."
    ),
    "Sorting": (
        "MUI Data Grid cycle: first selection ascending, second descending, third "
        "removes the sort. No column sorted by default. All columns sortable."
    ),
    "Empty state, tables": (
        'MUI Data Grid default text "No rows" in the center, unless a specific '
        "empty message is defined for that screen."
    ),
    "Empty state, lists and cards": (
        "The screen's specific empty text, or an empty state with no cards. State "
        "it explicitly."
    ),
    "Ordering of non-sorted lists, cards, or shortcuts": (
        "Provided by the backend. Use this ownership statement when order is not "
        "otherwise specified."
    ),
    "Ownership and source": (
        "When a value, grouping, mode, or URL is derived, name the system that "
        "determines it (backend, frontend, or external)."
    ),
    "External embedded UIs": (
        "Internal content and behavior are provided by that system and are out of "
        "scope. Authentication is handled in the background through single sign-on "
        "with no login screen. Error and recovery handling is owned by that system."
    ),
    "Non-functional or placeholder elements": (
        "State that the element is a placeholder for a later stage and does not "
        "create a working result. Decorative icons are visual indicators only and "
        "carry no functional meaning."
    ),
    "Validation": (
        "For each rule, state the rejected condition, the exact message in italics, "
        "and that the action does not complete. Capture the message text exactly as "
        "it appears in the UI or in an uploaded screenshot."
    ),
    "Transition behavior": (
        "For open, close, switch, reopen, and new actions, state what is cleared, "
        "what is kept, which embedded UI is closed, and which role or context "
        "governs subsequent messages and actions."
    ),
    "Multiple roles or personas": (
        "State whether content and values differ by role. Cover the single-role "
        "case, the admin-sees-all versus member-sees-own case, and the "
        "no-permission case."
    ),
}


# The six boundary categories of the completeness pass. Every AC describes a
# happy path; each category is a trigger question asked against it.
BOUNDARY_CATEGORIES: dict[int, str] = {
    1: (
        "Empty, none, zero — what is shown with no records, no matches, or no "
        "selection?"
    ),
    2: (
        "Set operation scope — for any search, filter, or sort: which fields, what "
        "match type, case sensitivity, what order?"
    ),
    3: (
        "Transition state and context — on open, close, switch, reopen, or new: "
        "what persists, what resets, and which role or context governs next?"
    ),
    4: (
        "Type and fallback — if an item maps to more than one bucket, to none, or "
        "needs a mode chosen: how is it decided?"
    ),
    5: (
        "Role and persona difference — when more than one role is named, does "
        "behavior or content differ?"
    ),
    6: (
        "Ownership and source — who determines, owns, or sources this value or "
        "behavior: backend, frontend, or an external system?"
    ),
}


# The 30-item review checklist. Items the renderer/linter settle mechanically are
# marked here so the model does not re-grade what code already decided; see
# ``jira_lint.DETERMINISTIC_ITEMS``.
CHECKLIST: dict[int, str] = {
    1: "Correct section order",
    2: "Uses As / I want to / So that",
    3: "Persona is specific",
    4: "So that shows business value",
    5: "Story covers all ACs",
    6: "Story is clear and concise",
    7: "AC title uses h3. *AC X- Title*",
    8: "Uses *GIVEN* that with lowercase that",
    9: "Keywords bold with single asterisks",
    10: "AND and BUT indented 2 spaces in all blocks",
    11: "Example text italic",
    12: "No separators between ACs",
    13: "No emojis or icons",
    14: "Jira markup not Markdown",
    15: "All ACs testable through observable output",
    16: "No non-observable ACs (technical tasks moved to Description)",
    17: "No hardcoded test data",
    18: "No invented information",
    19: "Descriptive language",
    20: "S.M.A.R.T. — Specific",
    21: "S.M.A.R.T. — Measurable",
    22: "S.M.A.R.T. — Achievable",
    23: "S.M.A.R.T. — Relevant",
    24: "S.M.A.R.T. — Testable",
    25: "Each list, table, and search states its empty and no-match result",
    26: "Each search, filter, and sort states fields, match type, case handling, order",
    27: "Each open/close/switch/reopen/new states what persists, what resets, which role",
    28: "Each derived value, grouping, mode, or URL names its owning system",
    29: "Each named role states whether behavior or content differs",
    30: "Each validation states the rejected condition, the exact message, and that the action does not complete",
}


def defaults_block() -> str:
    """The default table as prompt text, one row per line."""
    return "\n".join(f"- {concern}: {rule}" for concern, rule in PROJECT_DEFAULTS.items())


def categories_block() -> str:
    """The six boundary categories as prompt text."""
    return "\n".join(f"{index}. {text}" for index, text in BOUNDARY_CATEGORIES.items())


def checklist_block(items: list[int]) -> str:
    """The named checklist items as prompt text."""
    return "\n".join(f"{index}. {CHECKLIST[index]}" for index in items)
