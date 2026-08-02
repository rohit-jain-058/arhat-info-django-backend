"""
Base agent class. All specialist agents inherit from this.
Each agent has ONE job, ONE output schema, and signals when it's done.
"""
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    RUNNING   = "running"    # still gathering / working
    DONE      = "done"       # completed its job, ready to hand off
    NEEDS_MORE= "needs_more" # needs more info from user before continuing
    ESCALATE  = "escalate"   # project too complex — human needed


@dataclass
class AgentResult:
    """Standardised output from every agent."""
    agent_name:   str
    status:       AgentStatus
    output:       dict                        # structured JSON output
    message:      str                         # conversational message to show user
    next_agent:   str | None    = None        # which agent should run next
    confidence:   float         = 0.0         # 0.0 - 1.0 how confident agent is
    missing_info: list[str]     = field(default_factory=list)
    metadata:     dict          = field(default_factory=dict)


class BaseAgent(ABC):
    """
    Base class for all specialist agents.
    Each agent implements: run() → AgentResult
    """
    name:        str = "base"
    description: str = ""

    def __init__(self, openai_client=None, anthropic_client=None):
        self.openai    = openai_client
        self.anthropic = anthropic_client

    @abstractmethod
    def run(self, conversation_history: list[dict], context: dict) -> AgentResult:
        """
        Run the agent.
        conversation_history: full OpenAI-format message list
        context: accumulated project data from previous agents
        Returns AgentResult with status, output, and optional next agent
        """
        pass

    def _call_openai(self, system: str, messages: list[dict],
                     model: str = "gpt-4o", json_mode: bool = True,
                     max_tokens: int = 1500, temperature: float = 0.2) -> dict | str:
        """Helper — call OpenAI and return parsed JSON or raw text."""
        kwargs = dict(
            model    = model,
            messages = [{"role": "system", "content": system}] + messages,
            temperature = temperature,
            max_tokens  = max_tokens,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.openai.chat.completions.create(**kwargs)
        content  = response.choices[0].message.content

        if json_mode:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                logger.error(f"[{self.name}] JSON decode failed: {content[:200]}")
                return {}
        return content

    def _call_claude(self, prompt: str, system: str = None,
                     max_tokens: int = 2000) -> str:
        """Helper — call Anthropic Claude and return text."""
        messages = [{"role": "user", "content": prompt}]
        kwargs   = {"model": "claude-sonnet-4-20250514",
                    "max_tokens": max_tokens, "messages": messages}
        if system:
            kwargs["system"] = system

        message = self.anthropic.messages.create(**kwargs)
        return message.content[0].text

    def _stream_openai(self, system: str, messages: list[dict],
                       model: str = "gpt-4o", max_tokens: int = 600):
        """Helper — stream OpenAI tokens. Returns a generator."""
        stream = self.openai.chat.completions.create(
            model    = model,
            messages = [{"role": "system", "content": system}] + messages,
            stream   = True,
            temperature = 0.7,
            max_tokens  = max_tokens,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    def _build_transcript(self, history: list[dict], last_n: int = 12) -> str:
        recent = history[-last_n:] if len(history) > last_n else history
        return "\n".join([
            f"{m['role'].upper()}: {m['content']}"
            for m in recent
            if m['role'] in ('user', 'assistant')
        ])
