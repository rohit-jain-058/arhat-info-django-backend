"""
Requirements Agent — uses OpenAI.
Asks follow-up questions, extracts structured requirements,
signals DONE when completeness_score >= 0.75.
"""
import logging
from services.ai_service import openai_stream, openai_json
from prompts.prompts import (
    REQUIREMENTS_CHAT_PROMPT,
    REQUIREMENTS_EXTRACT_PROMPT,
    REQUIREMENTS_NEXT_QUESTION_PROMPT,
)

logger = logging.getLogger(__name__)


def stream_question(history: list):
    """
    Stream a conversational response token by token.
    Called during the requirements phase for live chat feel.
    """
    return openai_stream(
        system   = REQUIREMENTS_CHAT_PROMPT,
        messages = history,
        model    = "gpt-4o-mini",
    )


def extract(history: list) -> dict:
    """
    Extract structured requirements from full conversation history.
    Returns dict with completeness_score and ready_for_architecture flag.
    """
    transcript = "\n".join([
        f"{m['role'].upper()}: {m['content']}"
        for m in history
        if m['role'] in ('user', 'assistant')
    ])

    result = openai_json(
        system   = REQUIREMENTS_EXTRACT_PROMPT,
        messages = [{"role": "user", "content": f"Conversation:\n{transcript}"}],
        model    = "gpt-4o",
    )

    # Safe defaults if extraction partially fails
    result.setdefault("completeness_score",    0.0)
    result.setdefault("ready_for_architecture", False)
    result.setdefault("missing_info",          [])
    result.setdefault("core_features",         [])
    return result
def next_question3(history: list, requirements: dict) -> tuple[str, bool]:
    """
    Returns (question_text, is_done).
    If is_done is True the orchestrator should advance immediately.
    """
    import json

    bot_questions = [
        f"- {m['content']}"
        for m in history
        if m["role"] == "assistant"
    ]

    user_answers = [
        f"- {m['content']}"
        for m in history
        if m["role"] == "user"
    ]

    system = """You are deciding what single question to ask next OR whether to stop asking.

ALREADY ASKED BY BOT (do not repeat ANY of these):
{bot_questions}

USER ANSWERS SO FAR:
{user_answers}

WHAT WE KNOW:
{known}

If all important things are covered — stop asking and signal done.
Return JSON with two fields:
  "question": "your question here" (empty string if done)
  "is_done": true or false
""".format(
        bot_questions = "\n".join(bot_questions) if bot_questions else "Nothing yet",
        user_answers  = "\n".join(user_answers)  if user_answers  else "Nothing yet",
        known         = json.dumps({
            "project_type":      requirements.get("project_type"),
            "business_problem":  requirements.get("business_problem"),
            "target_users":      requirements.get("target_users"),
            "features":          [f.get("name") if isinstance(f, dict) else f
                                  for f in requirements.get("core_features", [])],
            "integrations":      requirements.get("integrations"),
            "auth_required":     requirements.get("auth_required"),
            "expected_users":    requirements.get("expected_users"),
            "budget":            requirements.get("budget_usd"),
            "timeline":          requirements.get("timeline_weeks"),
            "missing":           requirements.get("missing_info", []),
            "completeness":      requirements.get("completeness_score", 0),
        }, indent=2),
    )

    result = openai_json(
        system   = system + '\n\nReturn JSON: {"question": "...", "is_done": false}',
        messages = [{"role": "user", "content": "What should I ask next, or should I stop?"}],
        model    = "gpt-4o-mini",
    )

    is_done  = result.get("is_done", False)
    question = result.get("question", "").strip()

    if is_done or not question:
        return "", True

    return question, False
def next_question(history: list, requirements: dict) -> tuple[str, bool]:
    """
    Returns (message, is_done).
    message = next question OR closing statement
    is_done = True means bot has enough info, advance pipeline
    """
    import json

    # Build explicit lists so OpenAI can see exactly what was covered
    bot_messages = [
        f"[{i+1}] {m['content']}"
        for i, m in enumerate([m for m in history if m["role"] == "assistant"])
    ]
    user_messages = [
        f"[{i+1}] {m['content']}"
        for i, m in enumerate([m for m in history if m["role"] == "user"])
    ]

    prompt = f"""QUESTIONS ALREADY ASKED BY BOT:
{chr(10).join(bot_messages) if bot_messages else "None yet"}

USER ANSWERS:
{chr(10).join(user_messages) if user_messages else "None yet"}

WHAT IS KNOWN:
- Project type: {requirements.get("project_type", "unknown")}
- Business problem: {requirements.get("business_problem", "unknown")}
- Target users: {requirements.get("target_users", [])}
- Features: {[f.get("name") if isinstance(f, dict) else f for f in requirements.get("core_features", [])]}
- Integrations: {requirements.get("integrations", [])}
- Auth required: {requirements.get("auth_required")}
- Expected users: {requirements.get("expected_users")}
- Budget: {requirements.get("budget_usd")}
- Timeline: {requirements.get("timeline_weeks")}
- Completeness score: {requirements.get("completeness_score", 0)}

STILL MISSING:
{requirements.get("missing_info", [])}

Decide: should I ask another question or do I have enough to design the architecture?
Return JSON: {{"is_done": true/false, "message": "..."}}"""

    result = openai_json(
        system   = REQUIREMENTS_NEXT_QUESTION_PROMPT,
        messages = [{"role": "user", "content": prompt}],
        model    = "gpt-4o-mini",
    )

    is_done = result.get("is_done", False)
    message = result.get("message", "").strip()

    # Safety fallback
    if not message:
        if is_done:
            message = "Great, I have a clear picture of your project. Let me design the architecture now."
        else:
            message = "Do you have any existing systems this needs to connect with?"

    return message, is_done
def next_question2(history: list, requirements: dict) -> str:
    import json

    # Build explicit list of every question the bot already asked
    bot_questions = [
        f"- {m['content']}"
        for m in history
        if m["role"] == "assistant"
    ]

    # Build explicit list of every answer the user gave
    user_answers = [
        f"- {m['content']}"
        for m in history
        if m["role"] == "user"
    ]

    system = """You are deciding what single question to ask next to gather software project requirements.

RULES:
1. Read the ALREADY ASKED section carefully
2. Never ask about anything in that list again — not even a variation of it
3. Never ask about something the user already answered
4. Ask about the most important gap that has NOT been covered yet
5. If all important things are known, ask about scale or deployment
6. Keep this conversational and friendly and brief— imagine you're chatting with a founder who just wants to get their idea out of their head and into a plan. Be curious, helpful, and concise. Do NOT be robotic or formal. Do NOT ask multiple questions at once.
7. If all the important questions are asked and covered, please do not ask unnecessary questions just to ask — it's okay to be done.
8. Return JSON: {"question": "your single question here"}"""

    context = f"""ALREADY ASKED BY BOT:
{chr(10).join(bot_questions) if bot_questions else "Nothing yet"}

USER ANSWERS SO FAR:
{chr(10).join(user_answers) if user_answers else "Nothing yet"}

WHAT WE KNOW:
- Project type: {requirements.get("project_type", "unknown")}
- Problem: {requirements.get("business_problem", "unknown")}
- Users: {requirements.get("target_users", [])}
- Features: {[f.get("name") if isinstance(f, dict) else f for f in requirements.get("core_features", [])]}
- Integrations: {requirements.get("integrations", [])}
- Auth needed: {requirements.get("auth_required")}
- Expected users: {requirements.get("expected_users")}
- Budget: {requirements.get("budget_usd")}
- Timeline: {requirements.get("timeline_weeks")}
- Missing: {requirements.get("missing_info", [])}

Pick ONE question about something genuinely unknown from the above.
Do NOT repeat anything from ALREADY ASKED."""

    result = openai_json(
        system   = system,
        messages = [{"role": "user", "content": context}],
        model    = "gpt-4o-mini",
    )
    return result.get("question", "Do you have any existing systems this needs to connect with?")
def is_complete(requirements: dict, message_count: int = 0) -> bool:
    features = requirements.get("core_features", [])

    # Handle both list-of-dicts AND list-of-strings
    feature_count = 0
    for f in features:
        if isinstance(f, dict):
            if f.get("priority") in ("must_have", None, ""):
                feature_count += 1
        elif isinstance(f, str) and f.strip():
            feature_count += 1

    # Hard override — after 5 user messages move forward if basics exist
    if message_count >= 5:
        return (
            bool(requirements.get("business_problem"))
            and bool(requirements.get("target_users"))
            and feature_count >= 1
        )

    return (
        requirements.get("ready_for_architecture", False)
        and requirements.get("completeness_score", 0) >= 0.65
        and bool(requirements.get("business_problem"))
        and bool(requirements.get("target_users"))
        and feature_count >= 2
    )
