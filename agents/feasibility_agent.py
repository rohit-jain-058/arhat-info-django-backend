"""
Feasibility Agent — uses OpenAI.
Estimates cost, timeline, complexity, and prototype recommendation.
"""
import json
import logging
from services.ai_service import openai_json
from prompts.prompts import FEASIBILITY_PROMPT

logger = logging.getLogger(__name__)


def estimate(requirements: dict, architecture: dict) -> dict:
    """
    Returns cost, timeline, complexity, and prototype recommendation.
    """
    combined = (
        f"Requirements:\n{json.dumps(requirements, indent=2)[:1200]}\n\n"
        f"Architecture:\n{json.dumps(architecture, indent=2)[:1200]}"
    )

    result = openai_json(
        system   = FEASIBILITY_PROMPT,
        messages = [{"role": "user", "content": combined}],
        model    = "gpt-4o",
    )

    # Safe defaults
    result.setdefault("complexity",    "medium")
    result.setdefault("timeline",      {"total_weeks": 6})
    result.setdefault("cost_usd",      {"min": 5000, "max": 15000})
    result.setdefault("prototype",     {"recommended": True, "cost_usd": 300, "days": 7})
    return result


def build_summary_message(feasibility: dict) -> str:
    """Build a readable message from feasibility data to show the user."""
    tl   = feasibility.get("timeline",  {})
    cost = feasibility.get("cost_usd",  {})
    proto= feasibility.get("prototype", {})
    comp = feasibility.get("complexity","medium")

    msg = (
        f"**Complexity:** {comp.title()}\n"
        f"**Timeline:** {tl.get('total_weeks', '?')} weeks\n"
        f"**Investment:** ${cost.get('min', '?'):,} – ${cost.get('max', '?'):,}\n"
    )

    if proto.get("recommended"):
        msg += (
            f"\n💡 I recommend a **${proto.get('cost_usd', 300)} prototype** "
            f"({proto.get('days', 7)} days) to validate: {proto.get('validates', 'the core flow')}."
        )

    return msg
