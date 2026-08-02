"""
AI service — clean wrappers for OpenAI and Anthropic.
Both clients are lazy-loaded so Django settings are ready first.
"""
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

_openai_client    = None
_anthropic_client = None


def get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic_client


# ── OpenAI: stream tokens one by one ─────────────────────────────────
def openai_stream(system: str, messages: list, model: str = "gpt-4o-mini"):
    """
    Generator — yields tokens one by one.
    Used with Django StreamingHttpResponse for live chat.
    """
    try:
        stream = get_openai().chat.completions.create(
            model      = model,
            messages   = [{"role": "system", "content": system}] + messages,
            stream     = True,
            temperature= 0.7,
            max_tokens = 400,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    except Exception as e:
        logger.error(f"openai_stream error: {e}")
        yield "I ran into an issue — please try again."


# ── OpenAI: structured JSON output ───────────────────────────────────
def openai_json(system: str, messages: list, model: str = "gpt-4o") -> dict:
    """
    Returns a parsed dict.
    Use for requirement extraction, feasibility estimation.
    NOTE: system prompt must contain the word JSON for OpenAI json_mode to work.
    """
    try:
        response = get_openai().chat.completions.create(
            model           = model,
            messages        = [{"role": "system", "content": system}] + messages,
            response_format = {"type": "json_object"},
            temperature     = 0.1,
            max_tokens      = 1500,
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"openai_json error: {e}")
        return {}


# ── Claude: free-form text (architecture + proposal) ─────────────────
def claude_text(system: str, user_prompt: str, max_tokens: int = 2500) -> str:
    """
    Returns plain text from Claude Sonnet.
    Use for architecture design and proposal writing.
    """
    try:
        message = get_anthropic().messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = max_tokens,
            system     = system,           # NOTE: Claude uses a separate system param
            messages   = [{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text     # NOTE: .content[0].text, not .choices[0]
    except Exception as e:
        logger.error(f"claude_text error: {e}")
        return f"Architecture generation failed: {e}"


# ── Claude: parse JSON from response (strips ```json blocks) ─────────
def claude_json(system: str, user_prompt: str, max_tokens: int = 2500) -> dict:
    """
    Calls Claude and parses the JSON response.
    Claude doesn't have a native json_mode — we strip markdown fences manually.
    """
    raw = claude_text(system, user_prompt, max_tokens)
    # Strip ```json ... ``` blocks if present
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            candidate = part.lstrip("json").strip()
            if candidate.startswith("{"):
                raw = candidate
                break
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        logger.error(f"claude_json parse failed: {raw[:300]}")
        return {"raw_response": raw}
# ADD these two replacements:
def gpt_text(system: str, user_prompt: str, max_tokens: int = 2500) -> str:
    """Free-form text generation using OpenAI. Replaces claude_text."""
    try:
        response = get_openai().chat.completions.create(
            model      = "gpt-4o",
            messages   = [
                {"role": "system", "content": system},
                {"role": "user",   "content": user_prompt},
            ],
            temperature= 0.5,
            max_tokens = max_tokens,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"gpt_text error: {e}")
        return f"Generation failed: {e}"


def gpt_json(system: str, user_prompt: str, max_tokens: int = 2500) -> dict:
    """Structured JSON output using OpenAI. Replaces claude_json."""
    try:
        response = get_openai().chat.completions.create(
            model           = "gpt-4o",
            messages        = [
                {"role": "system", "content": system},
                {"role": "user",   "content": user_prompt},
            ],
            response_format = {"type": "json_object"},
            temperature     = 0.2,
            max_tokens      = max_tokens,
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"gpt_json error: {e}")
        return {}