"""
Requirements Agent — OpenAI gpt-4o
Responsibility: Talk to the client, ask intelligent follow-up questions,
extract structured requirements, and signal DONE when requirements are complete.

This agent OWNS the discovery + requirements phase.
It decides when enough information has been gathered to hand off to Architecture.
"""
import logging
from .base_agent import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior business analyst and requirement engineer for Arhatinfo — a backend, AI automation, and cloud engineering agency.

Your ONLY job right now: understand the client's project thoroughly enough to hand it to an architect.

How you work:
1. Start by understanding the business problem (not the technical solution)
2. Ask ONE focused question at a time — never overwhelm with multiple questions
3. Dig into: users, integrations, scale, auth, real-time needs, existing systems
4. Do NOT suggest solutions — just gather requirements
5. When you have enough information, signal that requirements are complete

Signs requirements are complete:
- You know the core business problem
- You know who the users are
- You know the key features (at least 3)
- You know about integrations and data needs
- You know scale expectations
- Budget/timeline is roughly known

Be conversational and professional. Reference what the client said."""

EXTRACTION_PROMPT = """Extract ALL project requirements from this conversation into structured JSON.

Return this exact structure:
{
  "project_name": null,
  "project_type": "saas|marketplace|api|automation|ai_tool|website|mobile|data_pipeline|other",
  "business_problem": "1-sentence description",
  "target_users": ["user type 1"],
  "core_features": [
    {"name": "...", "description": "...", "priority": "must_have|nice_to_have|future", "complexity": "low|medium|high"}
  ],
  "modules": ["Module 1", "Module 2"],
  "integrations": ["Stripe", "Slack"],
  "auth_required": true,
  "auth_types": ["email", "oauth", "sso"],
  "admin_panel": true,
  "file_uploads": false,
  "real_time": false,
  "mobile_required": false,
  "api_needed": true,
  "expected_users": "number or range",
  "data_sensitivity": "public|internal|sensitive|hipaa|pci",
  "tech_preferences": [],
  "budget_usd": {"min": null, "max": null},
  "timeline_weeks": null,
  "existing_systems": [],
  "geographic_scope": "local|national|global",
  "completeness_score": 0.85,
  "missing_info": ["Still need to know X"],
  "ready_for_architecture": false
}

Set ready_for_architecture to true ONLY when:
- business_problem is filled
- target_users has at least 1 entry
- core_features has at least 3 must_have features
- completeness_score >= 0.80

Return ONLY valid JSON."""

NEXT_QUESTION_PROMPT = """You are gathering software project requirements.

Based on the conversation so far and the extracted requirements, ask the SINGLE most important missing question.
The question should help size and architect the project.

Priority order:
1. Core business problem (if unclear)
2. Who are the users
3. Key features
4. User scale expectations
5. Integrations needed
6. Real-time requirements
7. Budget/timeline

Return ONLY the question — no preamble, no explanation."""


class RequirementsAgent(BaseAgent):
    name        = "requirements"
    description = "Gathers and finalises project requirements through intelligent conversation"

    def run(self, conversation_history: list[dict], context: dict) -> AgentResult:
        """
        Two modes:
        1. Extract current requirements and assess completeness
        2. Generate next question if incomplete, or signal DONE if complete
        """
        transcript = self._build_transcript(conversation_history)

        # ── Step 1: Extract structured requirements ────────────────────
        requirements = self._call_openai(
            system     = EXTRACTION_PROMPT,
            messages   = [{"role": "user", "content": f"Conversation:\n{transcript}"}],
            model      = "gpt-4o",
            json_mode  = True,
            max_tokens = 1500,
            temperature= 0.1,
        )

        if not requirements:
            requirements = {"completeness_score": 0.0, "ready_for_architecture": False}

        completeness      = requirements.get("completeness_score", 0.0)
        ready             = requirements.get("ready_for_architecture", False)
        missing           = requirements.get("missing_info", [])

        # ── Step 2: Decide status ──────────────────────────────────────
        if ready and completeness >= 0.80:
            # Requirements complete — hand off to architecture
            message = self._generate_handoff_message(requirements)
            return AgentResult(
                agent_name   = self.name,
                status       = AgentStatus.DONE,
                output       = requirements,
                message      = message,
                next_agent   = "architecture",
                confidence   = completeness,
                missing_info = missing,
            )

        # ── Step 3: Ask next clarifying question ───────────────────────
        context_str = f"Transcript:\n{transcript}\n\nExtracted so far:\n{requirements}"
        next_q = self._call_openai(
            system     = NEXT_QUESTION_PROMPT,
            messages   = [{"role": "user", "content": context_str}],
            model      = "gpt-4o-mini",
            json_mode  = False,
            max_tokens = 150,
            temperature= 0.4,
        )

        return AgentResult(
            agent_name   = self.name,
            status       = AgentStatus.NEEDS_MORE,
            output       = requirements,
            message      = next_q or "Could you tell me more about the main users of this system?",
            next_agent   = None,   # stay on requirements
            confidence   = completeness,
            missing_info = missing,
        )

    def _generate_handoff_message(self, req: dict) -> str:
        """Generate a friendly message signalling requirements are complete."""
        features = req.get("core_features", [])
        n        = len([f for f in features if f.get("priority") == "must_have"])
        name     = req.get("project_type", "project").replace("_", " ")
        return (
            f"I have a clear picture of your {name} now — "
            f"{n} core features, {req.get('project_type', 'full stack')} architecture needed. "
            f"Let me hand this to our architecture agent to design the right system for you."
        )

    def stream_conversational_response(self, conversation_history: list[dict]) -> str:
        """
        Stream a warm, conversational response while the extraction runs in background.
        Used for the initial few messages before extraction kicks in.
        """
        return self._stream_openai(
            system   = SYSTEM_PROMPT,
            messages = conversation_history,
            model    = "gpt-4o",
            max_tokens = 400,
        )
