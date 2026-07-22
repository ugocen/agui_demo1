"""Deterministic format linter over a rendered artifact.

The 30-item review checklist splits cleanly in two. The FORMAT half — section
order, heading shape, keyword casing, indentation, separators, Markdown leaks —
is decidable by reading the text, so it is decided here with regex and the model
is never asked to grade it. The CONTENT half (is this AC testable? is the
persona specific? does the story cover every AC?) needs judgment and stays with
the model.

Grading format with an LLM is the failure mode this replaces: it agrees the
indent is two spaces when it is three, because it is reading its own intent
rather than the bytes. Code cannot do that.

Item 17 is the one honest exception. "No hardcoded test data" has no decidable
boundary — an order number in an example may be exactly the literal the spec
forbids or a legitimate quoted UI string — so it reports ``REVIEW`` with the
tokens it found rather than claiming a verdict it cannot support.
"""

import re

from defaults import CHECKLIST
from jira_render import SECTION_ORDER

# Items this module decides. Everything else in CHECKLIST is graded by the model.
DETERMINISTIC_ITEMS: list[int] = [1, 7, 8, 9, 10, 11, 12, 13, 14, 17]

PASS = "PASS"
FAIL = "FAIL"
REVIEW = "REVIEW"

# One anchor per renderable section, in the spec's fixed order.
_SECTION_ANCHORS: list[tuple[str, re.Pattern[str]]] = [
    ("title", re.compile(r"^h1\. \S")),
    ("version", re.compile(r"^_Document Version: ")),
    ("user_story", re.compile(r"^h2\. User Story$")),
    ("problem_statement", re.compile(r"^\*Problem Statement:\*$")),
    ("backend_notes", re.compile(r"^\*Backend Tasks or Notes:\*$")),
    ("frontend_notes", re.compile(r"^\*Frontend Tasks or Notes:\*$")),
    ("infra_notes", re.compile(r"^\*Infrastructure Tasks or Notes:\*$")),
    ("additional_notes", re.compile(r"^\*Additional Notes\*$")),
    ("nfrs", re.compile(r"^\*Non-Functional Requirements\*$")),
    ("out_of_scope", re.compile(r"^\*Out of Scope\*$")),
    ("acceptance_criteria", re.compile(r"^h2\. Acceptance Criteria$")),
]

_AC_TITLE = re.compile(r"^h3\. \*AC (\d+)- (.+)\*$")
_AC_TITLE_LOOSE = re.compile(r"^h3\.\s*\*?\s*AC\s*([\d.]+)\s*[-–—]", re.IGNORECASE)
_KEYWORD_LINE = re.compile(r"^(\s*)\*(GIVEN|WHEN|THEN|AND|BUT)\*")
_BOLD_KEYWORD_DOUBLE = re.compile(r"\*\*(GIVEN|WHEN|THEN|AND|BUT)\*\*")
_BARE_KEYWORD = re.compile(r"^\s*(GIVEN|WHEN|THEN|AND|BUT)\b")
_GIVEN_THAT = re.compile(r"^\*GIVEN\* (?!that\b)")
_GIVEN_THAT_WRONG_CASE = re.compile(r"^\*GIVEN\* (That|THAT)\b")
# A quoted run that is not wrapped in the Jira italic underscore.
_UNITALIC_QUOTE = re.compile(r'(?<!_)"[^"\n]{2,}"(?!_)')
_EMOJI = re.compile(
    "["
    "\U0001f000-\U0001faff"  # pictographs, emoticons, transport, symbols
    "☀-➿"  # misc symbols + dingbats
    "️"  # variation selector-16
    "⬀-⯿"  # arrows/stars
    "]"
)
_MARKDOWN_BOLD = re.compile(r"\*\*[^*\n]+\*\*")
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s")
_MARKDOWN_BULLET = re.compile(r"^\s*\*\s")
_MARKDOWN_LINK = re.compile(r"\[[^\]\n]+\]\([^)\n]+\)")
_MARKDOWN_FENCE = re.compile(r"^```")
# Conservative literal-data probes; each match is reported, never auto-failed.
_LITERALS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),  # email address
    re.compile(r"https?://\S+"),  # url
    re.compile(r"#\d{2,}"),  # ticket / record id
    re.compile(r"\b\d{4,}\b"),  # long bare number
]


def _result(item: int, status: str, detail: str = "") -> dict:
    return {"item": item, "name": CHECKLIST[item], "status": status, "detail": detail}


def _check_section_order(lines: list[str]) -> dict:
    seen: list[str] = []
    for line in lines:
        for name, pattern in _SECTION_ANCHORS:
            if pattern.match(line) and name not in seen:
                seen.append(name)
    expected = [name for name in SECTION_ORDER if name in seen]
    if seen != expected:
        return _result(1, FAIL, f"section order is {seen}, expected {expected}")
    missing = [name for name in ("title", "user_story", "acceptance_criteria") if name not in seen]
    if missing:
        return _result(1, FAIL, f"required section(s) missing: {', '.join(missing)}")
    return _result(1, PASS)


def _check_ac_titles(lines: list[str]) -> dict:
    numbers: list[int] = []
    problems: list[str] = []
    for line in lines:
        strict = _AC_TITLE.match(line)
        if strict:
            numbers.append(int(strict.group(1)))
            continue
        loose = _AC_TITLE_LOOSE.match(line)
        if loose:
            label = loose.group(1)
            if "." in label:
                problems.append(f"sub-numbered AC {label} (flat numbering only)")
            else:
                problems.append(f"malformed AC title: {line!r}")
    if not numbers and not problems:
        return _result(7, FAIL, "no acceptance criteria found")
    if numbers != list(range(1, len(numbers) + 1)):
        problems.append(f"numbering is {numbers}, expected {list(range(1, len(numbers) + 1))}")
    return _result(7, FAIL, "; ".join(problems)) if problems else _result(7, PASS)


def _check_given_that(lines: list[str]) -> dict:
    problems = [
        f"line {index}: {line!r}"
        for index, line in enumerate(lines, start=1)
        if line.startswith("*GIVEN*")
        and (_GIVEN_THAT.match(line) or _GIVEN_THAT_WRONG_CASE.match(line))
    ]
    if not any(line.startswith("*GIVEN*") for line in lines):
        return _result(8, FAIL, "no *GIVEN* line found")
    return _result(8, FAIL, "; ".join(problems)) if problems else _result(8, PASS)


def _check_keyword_bold(lines: list[str]) -> dict:
    problems: list[str] = []
    for index, line in enumerate(lines, start=1):
        if _BOLD_KEYWORD_DOUBLE.search(line):
            problems.append(f"line {index}: double-asterisk keyword")
        elif _BARE_KEYWORD.match(line) and not _KEYWORD_LINE.match(line):
            problems.append(f"line {index}: unbolded keyword {line.strip()[:40]!r}")
    return _result(9, FAIL, "; ".join(problems)) if problems else _result(9, PASS)


def _check_indent(lines: list[str]) -> dict:
    problems = [
        f"line {index}: {len(match.group(1))} space(s) before *{match.group(2)}*"
        for index, line in enumerate(lines, start=1)
        if (match := _KEYWORD_LINE.match(line))
        and match.group(2) in ("AND", "BUT")
        and match.group(1) != "  "
    ]
    return _result(10, FAIL, "; ".join(problems)) if problems else _result(10, PASS)


def _check_italic_examples(lines: list[str]) -> dict:
    problems = [
        f"line {index}: {match.group(0)[:40]!r} is not italic (use _\"…\"_)"
        for index, line in enumerate(lines, start=1)
        if (match := _UNITALIC_QUOTE.search(line))
    ]
    return _result(11, FAIL, "; ".join(problems)) if problems else _result(11, PASS)


def _check_no_ac_separators(lines: list[str]) -> dict:
    try:
        start = next(i for i, line in enumerate(lines) if line == "h2. Acceptance Criteria")
    except StopIteration:
        return _result(12, FAIL, "no Acceptance Criteria section")
    offenders = [i + 1 for i, line in enumerate(lines[start:], start=start) if line.strip() == "----"]
    if offenders:
        return _result(12, FAIL, f"separator line(s) inside Acceptance Criteria at {offenders}")
    return _result(12, PASS)


def _check_no_emoji(text: str) -> dict:
    found = sorted({match.group(0) for match in _EMOJI.finditer(text)})
    return _result(13, FAIL, f"emoji found: {' '.join(found)}") if found else _result(13, PASS)


def _check_jira_not_markdown(lines: list[str]) -> dict:
    problems: list[str] = []
    for index, line in enumerate(lines, start=1):
        if _MARKDOWN_BOLD.search(line):
            problems.append(f"line {index}: Markdown **bold**")
        if _MARKDOWN_HEADING.match(line):
            problems.append(f"line {index}: Markdown heading")
        if _MARKDOWN_BULLET.match(line):
            problems.append(f"line {index}: Markdown '*' bullet (use '-')")
        if _MARKDOWN_LINK.search(line):
            problems.append(f"line {index}: Markdown link")
        if _MARKDOWN_FENCE.match(line):
            problems.append(f"line {index}: Markdown code fence")
    return _result(14, FAIL, "; ".join(problems)) if problems else _result(14, PASS)


def _check_literals(lines: list[str]) -> dict:
    # Scoped to the Acceptance Criteria section on purpose. "No hardcoded test
    # data" is a rule about what QA is asked to verify, and the header's
    # `_Last Updated: 2026-07-22_` is metadata, not test data — scanning the whole
    # document reported the year as a finding on every single run.
    try:
        start = next(i for i, line in enumerate(lines) if line == "h2. Acceptance Criteria")
    except StopIteration:
        return _result(17, PASS)

    hits: list[str] = []
    for index, line in enumerate(lines[start:], start=start + 1):
        # Quoted UI text is legitimate — it is real message text, not test data.
        stripped = re.sub(r'_"[^"\n]*"_', "", line)
        for pattern in _LITERALS:
            hits += [f"line {index}: {match.group(0)}" for match in pattern.finditer(stripped)]
    if not hits:
        return _result(17, PASS)
    return _result(
        17,
        REVIEW,
        "possible hardcoded test data — confirm each is descriptive, not literal: "
        + "; ".join(hits[:8]),
    )


def lint_document(document: str) -> dict:
    """Run every deterministic checklist item over a rendered artifact.

    Returns ``{"items": [...], "failed": [...], "review": [...], "passed": n,
    "total": n}``. ``failed`` is what the agent must repair before the artifact
    is final; ``review`` is what it must confirm but may keep.
    """
    lines = document.splitlines()
    items = [
        _check_section_order(lines),
        _check_ac_titles(lines),
        _check_given_that(lines),
        _check_keyword_bold(lines),
        _check_indent(lines),
        _check_italic_examples(lines),
        _check_no_ac_separators(lines),
        _check_no_emoji(document),
        _check_jira_not_markdown(lines),
        _check_literals(lines),
    ]
    items.sort(key=lambda entry: entry["item"])
    return {
        "items": items,
        "failed": [entry for entry in items if entry["status"] == FAIL],
        "review": [entry for entry in items if entry["status"] == REVIEW],
        "passed": sum(1 for entry in items if entry["status"] == PASS),
        "total": len(items),
    }
