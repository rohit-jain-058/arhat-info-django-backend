"""
Feasibility Agent — OpenAI gpt-4o
Responsibility: Assess technical feasibility, estimate timeline and cost,
identify risks. Runs after Architecture Agent.
"""
import json
import logging
from .base_agent import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

FEASIBILITY_PROMPT = """You are a senior project manager and technical lead at Arhatinfo.

Given the project requirements and proposed architecture, provide a detailed feasibility assessment and cost estimate.

Be honest and slightly conservative — under-promise and over-deliver.

Return this JSON:
{
  "feasibility": "high | medium | low",
  "feasibility_summary": "2-sentence honest assessment",

  "complexity": "small | medium | large | complex",
  "complexity_factors": ["Factor 1", "Factor 2"],

  "timeline": {
    "phase_1_foundation_weeks": 1,
    "phase_2_core_weeks": 3,
    "phase_3_qa_deploy_weeks": 1,
    "total_weeks": 5,
    "confidence": "high | medium | low",
    "risks_that_could_extend": ["Integration complexity", "Scope creep"]
  },

  "cost_usd": {
    "min": 8000,
    "max": 15000,
    "breakdown": {
      "design_discovery": 1500,
      "backend_development": 6000,
      "frontend_development": 4000,
      "devops_deployment": 1000,
      "qa_testing": 1500,
      "project_management": 1000
    },
    "monthly_infrastructure_usd": 150,
    "confidence": "medium"
  },

  "team_needed": {
    "backend_engineer": 1,
    "frontend_engineer": 1,
    "ai_engineer": 0,
    "devops": 0,
    "designer": 0,
    "project_manager": 1
  },

  "risks": [
    {
      "risk": "Third-party API rate limits",
      "probability": "medium",
      "impact": "high",
      "mitigation": "Implement caching and queue-based processing"
    }
  ],

  "prototype_recommendation": {
    "recommended": true,
    "scope": "Core feature X to validate the main user flow",
    "timeline_days": 7,
    "cost_usd": 300,
    "validates": ["Main user flow", "Key integration"]
  },

  "recommended_start": "prototype | full_project | discovery_call",
  "start_reasoning": "Why this start is recommended"
}

Return ONLY valid JSON."""


class FeasibilityAgent(BaseAgent):
    name        = "feasibility"
    description = "Assesses feasibility, estimates cost and timeline using OpenAI"

    def run(self, conversation_history: list[dict], context: dict) -> AgentResult:
        requirements = context.get("requirements", {})
        architecture = context.get("architecture", {})

        if not architecture:
            return AgentResult(
                agent_name = self.name,
                status     = AgentStatus.NEEDS_MORE,
                output     = {},
                message    = "Architecture needs to be designed first.",
                next_agent = "architecture",
                confidence = 0.0,
            )

        combined = (
            f"Requirements:\n{json.dumps(requirements, indent=2)[:1500]}\n\n"
            f"Architecture:\n{json.dumps(architecture, indent=2)[:1500]}"
        )

        result = self._call_openai(
            system     = FEASIBILITY_PROMPT,
            messages   = [{"role": "user", "content": combined}],
            model      = "gpt-4o",
            json_mode  = True,
            max_tokens = 1500,
            temperature= 0.1,
        )

        # Build conversational summary
        feasibility = result.get("feasibility", "medium")
        total_weeks = result.get("timeline", {}).get("total_weeks", "?")
        cost_min    = result.get("cost_usd", {}).get("min", "?")
        cost_max    = result.get("cost_usd", {}).get("max", "?")
        complexity  = result.get("complexity", "medium")
        proto       = result.get("prototype_recommendation", {})

        message = (
            f"📊 **Feasibility: {feasibility.upper()}** — {result.get('feasibility_summary', '')}\n\n"
            f"**Complexity:** {complexity.title()}\n"
            f"**Timeline:** {total_weeks} weeks\n"
            f"**Investment:** ${cost_min:,} – ${cost_max:,}\n\n"
        )

        if proto.get("recommended"):
            message += (
                f"💡 I recommend starting with a **${proto.get('cost_usd', 300)} prototype** "
                f"({proto.get('timeline_days', 7)} days) to validate: {proto.get('validates', ['the core flow'])[0]}.\n\n"
            )

        message += "Let me now generate your full project proposal."

        return AgentResult(
            agent_name = self.name,
            status     = AgentStatus.DONE,
            output     = result,
            message    = message,
            next_agent = "proposal",
            confidence = 0.88,
        )
