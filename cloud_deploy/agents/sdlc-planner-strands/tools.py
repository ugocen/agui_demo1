"""Tools for the SDLC Planner agent.

Each tool matches one card in the card catalog (doc 07 section 4).
The tool input is the card payload: tools validate and shape it, the LLM
decides the content.

request_ticket_approval is intentionally NOT defined here. It is a
human-in-the-loop tool owned by the frontend: CopilotKit sends its
definition in RunAgentInput.tools, ag-ui-strands registers it as a client
proxy tool, and the run pauses until the browser returns the decision.
"""

from strands import tool

VALID_PRIORITIES = {"high", "medium", "low"}
VALID_CONFIDENCE = {"high", "medium", "low"}

TICKET_APPROVAL_TOOL_NAME = "request_ticket_approval"


@tool
def show_user_stories(stories: list[dict]) -> dict:
    """Display drafted user stories as cards in the UI. Call exactly once with all stories.

    Args:
        stories: List of story objects. Each object has keys:
            id (string, e.g. "US-1"),
            title (string),
            acceptance_criteria (list of strings),
            priority (one of "high", "medium", "low").
    """
    if not isinstance(stories, list) or not stories:
        raise ValueError("stories must be a non-empty list")
    shaped = []
    for index, story in enumerate(stories):
        if not isinstance(story, dict):
            raise ValueError("each story must be an object")
        priority = str(story.get("priority", "medium")).lower()
        if priority not in VALID_PRIORITIES:
            priority = "medium"
        criteria = story.get("acceptance_criteria") or []
        if not isinstance(criteria, list):
            criteria = [str(criteria)]
        shaped.append(
            {
                "id": str(story.get("id") or f"US-{index + 1}"),
                "title": str(story.get("title", "")).strip(),
                "acceptance_criteria": [str(item) for item in criteria],
                "priority": priority,
            }
        )
    return {"stories": shaped}


@tool
def show_estimates(items: list[dict]) -> dict:
    """Display story point estimates as a table in the UI. Cover every current story id.

    Args:
        items: List of estimate objects. Each object has keys:
            story_id (string matching a story id shown earlier),
            points (number, story points),
            confidence (one of "high", "medium", "low").
    """
    if not isinstance(items, list) or not items:
        raise ValueError("items must be a non-empty list")
    shaped = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each estimate must be an object")
        confidence = str(item.get("confidence", "medium")).lower()
        if confidence not in VALID_CONFIDENCE:
            confidence = "medium"
        try:
            points = float(item.get("points", 0))
        except (TypeError, ValueError):
            raise ValueError("points must be a number")
        if points == int(points):
            points = int(points)
        shaped.append(
            {
                "story_id": str(item.get("story_id", "")),
                "points": points,
                "confidence": confidence,
            }
        )
    return {"items": shaped}
