"""
AI service — all OpenAI and Anthropic calls.
Keys come from Django settings (loaded from .env).
"""
import json
import logging
from django.conf import settings
from openai import OpenAI
import anthropic
# services/ai_service.py

from prompts.prompts import (
    CONSULTANT_SYSTEM_PROMPT,
    INTENT_DETECTION_PROMPT,
    REQUIREMENT_EXTRACTION_PROMPT,
    ARCHITECTURE_PROMPT,
    ESTIMATION_PROMPT,
    CLARIFICATION_PROMPT,
    ESCALATION_PROMPT,
    PROPOSAL_PROMPT,
)

logger = logging.getLogger(__name__)

# ── Clients (lazy init so Django settings are loaded first) ───────────
_openai_client    = None
_anthropic_client = None




CHAT_MODEL       = "gpt-4o"
FAST_MODEL       = "gpt-4o-mini"
STRUCTURED_MODEL = "gpt-4o"

FALLBACK_QUESTIONS = [
    "Do you have any existing systems or APIs this needs to connect with?",
    "What is your target timeline, and do you have a rough budget in mind?",
    "Will users need accounts and role-based access, or is this a single-user tool?",
    "Are there specific performance requirements — like expected concurrent users?",
    "Is there anything technically unusual about this project we should know upfront?",
]


# ── STREAMING CHAT ────────────────────────────────────────────────────
def stream_chat_response(messages: list, system_override: str = None):
    """
    Generator that yields response tokens one by one.
    Used with Django StreamingHttpResponse.
    """
    system = system_override or CONSULTANT_SYSTEM_PROMPT
    try:
        stream = get_openai().chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "system", "content": system}] + messages,
            stream=True,
            temperature=0.7,
            max_tokens=800,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield "\n\nI'm having a moment — please try again."


# ── DETECT INTENT ─────────────────────────────────────────────────────
def detect_intent(user_message: str) -> dict:
    try:
        response = get_openai().chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": INTENT_DETECTION_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Intent detection error: {e}")
        return {"intent": "other", "urgency": "medium", "has_budget": False,
                "has_timeline": False, "is_technical": False}


# ── EXTRACT REQUIREMENTS ──────────────────────────────────────────────
def extract_requirements(conversation_history: list) -> dict:
    transcript = "\n".join([
        f"{m['role'].upper()}: {m['content']}"
        for m in conversation_history
        if m['role'] in ('user', 'assistant')
    ])
    try:
        response = get_openai().chat.completions.create(
            model=STRUCTURED_MODEL,
            messages=[
                {"role": "system", "content": REQUIREMENT_EXTRACTION_PROMPT},
                {"role": "user",   "content": f"Conversation:\n{transcript}"},
            ],
            temperature=0.1,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Requirement extraction error: {e}")
        return {"error": str(e), "missing_info": ["Could not extract requirements"]}


# ── SUGGEST ARCHITECTURE ──────────────────────────────────────────────
def suggest_architecture(requirements: dict) -> dict:
    try:
        response = get_openai().chat.completions.create(
            model=STRUCTURED_MODEL,
            messages=[
                {"role": "system", "content": ARCHITECTURE_PROMPT},
                {"role": "user",   "content": f"Requirements:\n{json.dumps(requirements, indent=2)}"},
            ],
            temperature=0.2,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Architecture error: {e}")
        return {"error": str(e)}


# ── ESTIMATE PROJECT ──────────────────────────────────────────────────
def estimate_project(requirements: dict, architecture: dict) -> dict:
    try:
        response = get_openai().chat.completions.create(
            model=STRUCTURED_MODEL,
            messages=[
                {"role": "system", "content": ESTIMATION_PROMPT},
                {"role": "user",   "content": (
                    f"Requirements:\n{json.dumps(requirements, indent=2)}\n\n"
                    f"Architecture:\n{json.dumps(architecture, indent=2)}"
                )},
            ],
            temperature=0.1,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Estimation error: {e}")
        return {"error": str(e)}


# ── CLARIFYING QUESTION ───────────────────────────────────────────────
def get_clarifying_question(conversation_history: list, current_requirements: dict) -> str:
    context = (
        "Conversation so far:\n"
        + "\n".join([f"{m['role'].upper()}: {m['content']}" for m in conversation_history[-6:]])
        + f"\n\nCurrent requirements:\n{json.dumps(current_requirements, indent=2)}"
    )
    try:
        response = get_openai().chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": CLARIFICATION_PROMPT},
                {"role": "user",   "content": context},
            ],
            temperature=0.4,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Clarification error: {e}")
        return "Could you tell me more about the main users of this system?"


# ── ESCALATION CHECK ──────────────────────────────────────────────────
def should_escalate(conversation_history: list) -> dict:
    transcript = "\n".join([
        f"{m['role'].upper()}: {m['content']}"
        for m in conversation_history[-10:]
    ])
    try:
        response = get_openai().chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": ESCALATION_PROMPT},
                {"role": "user",   "content": transcript},
            ],
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Escalation error: {e}")
        return {"should_escalate": False, "reason": "Detection failed", "urgency": "normal"}


# ── GENERATE PROPOSAL ─────────────────────────────────────────────────
def generate_proposal(requirements: dict, architecture: dict, estimation: dict) -> str:
    """Uses Anthropic Claude for high-quality proposal writing. Falls back to OpenAI."""
    context = (
        f"Requirements:\n{json.dumps(requirements, indent=2)}\n\n"
        f"Architecture:\n{json.dumps(architecture, indent=2)}\n\n"
        f"Estimation:\n{json.dumps(estimation, indent=2)}"
    )

    # Try Anthropic first
    try:
        message = get_anthropic().messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": f"{PROPOSAL_PROMPT}\n\n{context}"}],
        )
        return message.content[0].text
    except Exception as e:
        logger.warning(f"Anthropic unavailable, falling back to OpenAI: {e}")

    # Fallback to OpenAI
    try:
        response = get_openai().chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": PROPOSAL_PROMPT},
                {"role": "user",   "content": context},
            ],
            temperature=0.5,
            max_tokens=2000,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Proposal generation error: {e}")
        return "Proposal generation failed. Please contact hello@arhatinfo.com."


# ── PHASE DETECTION ───────────────────────────────────────────────────
def detect_phase(message_count: int, requirements: dict) -> str:
    missing  = requirements.get("missing_info", [])
    features = requirements.get("features",    [])
    if message_count < 3:
        return "discovery"
    elif missing and len(missing) > 2:
        return "requirements"
    elif features and len(features) >= 2:
        return "architecture"
    return "requirements"


# Lazy clients — only created when first called
_openai    = None
_anthropic = None

def get_openai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai

def get_anthropic() -> anthropic.Anthropic:
    global _anthropic
    if _anthropic is None:
        _anthropic = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic


# ── OpenAI: stream tokens ─────────────────────────────────────────────
def openai_stream(system: str, messages: list, model="gpt-4o-mini"):
    """Generator — yields tokens one by one for StreamingHttpResponse."""
    stream = get_openai().chat.completions.create(
        model      = model,
        messages   = [{"role":"system","content":system}] + messages,
        stream     = True,
        temperature= 0.7,
        max_tokens = 400,
    )
    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


# ── OpenAI: structured JSON output ───────────────────────────────────
def openai_json(system: str, messages: list, model="gpt-4o") -> dict:
    """Returns a parsed dict. Use for requirement extraction, estimation."""
    import json
    response = get_openai().chat.completions.create(
        model           = model,
        messages        = [{"role":"system","content":system}] + messages,
        response_format = {"type": "json_object"},
        temperature     = 0.1,
        max_tokens      = 1500,
    )
    return json.loads(response.choices[0].message.content)


# ── Claude: structured or free-form text ─────────────────────────────
def claude_generate(system: str, user_prompt: str, max_tokens=2500) -> str:
    """Returns plain text. Use for architecture design and proposal writing."""
    message = get_anthropic().messages.create(
        model      = "claude-sonnet-4-20250514",
        max_tokens = max_tokens,
        system     = system,
        messages   = [{"role":"user","content":user_prompt}],
    )
    return message.content[0].text