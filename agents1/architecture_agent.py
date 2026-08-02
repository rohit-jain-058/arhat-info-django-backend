"""
Architecture Agent — Anthropic Claude Sonnet
Responsibility: Take finalized requirements and design a complete, production-ready
system architecture. Output structured architecture JSON + a clear explanation.

This agent runs ONCE when requirements are complete.
It uses Claude (not OpenAI) because Claude is better at long-form technical reasoning.
"""
import logging
from .base_agent import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

ARCHITECTURE_SYSTEM = """You are a principal software architect at Arhatinfo with 15 years experience building production systems.

You specialize in:
- Python backend systems (Django, FastAPI)
- AI/ML integration (OpenAI, Anthropic, LangChain)
- Cloud infrastructure (AWS, Docker, PostgreSQL, Redis)
- Scalable SaaS architecture

Your job: Given project requirements, design a complete, practical architecture that:
1. Solves the actual business problem
2. Is achievable within the estimated budget and timeline
3. Uses appropriate technology (not over-engineered)
4. Considers scale, security, and maintenance
5. Gives clear rationale for every decision

IMPORTANT: Be opinionated. Recommend specific tools, not generic descriptions.
If Redis is needed, say Redis. If Celery is needed, say Celery."""

ARCHITECTURE_PROMPT_TEMPLATE = """Design a complete production architecture for this project.

Project Requirements:
{requirements_json}

Return a structured JSON with:
{{
  "system_name": "Name of the system",
  "architecture_pattern": "Monolith | Modular Monolith | Microservices | Serverless",
  "pattern_reasoning": "Why this pattern fits",

  "tech_stack": {{
    "frontend": {{"technology": "React.js", "reason": "..."}},
    "backend": {{"technology": "Django REST", "reason": "..."}},
    "database": {{"primary": "PostgreSQL", "secondary": null, "reason": "..."}},
    "cache": {{"technology": "Redis", "reason": "...", "needed": true}},
    "queue": {{"technology": "Celery + Redis", "reason": "...", "needed": false}},
    "storage": {{"technology": "AWS S3", "reason": "...", "needed": false}},
    "ai_layer": {{"technology": "OpenAI API", "reason": "...", "needed": false}},
    "search": {{"technology": null, "reason": "...", "needed": false}},
    "deployment": {{"technology": "Docker + AWS EC2", "reason": "..."}}
  }},

  "modules": [
    {{
      "name": "User Management",
      "responsibility": "Auth, profiles, permissions",
      "api_endpoints": ["POST /auth/register", "POST /auth/login"],
      "models": ["User", "Profile", "Permission"],
      "estimated_weeks": 1,
      "depends_on": []
    }}
  ],

  "database_design": {{
    "key_tables": [
      {{"name": "users", "columns": ["id", "email", "..."], "notes": "..."}}
    ],
    "relationships": ["users 1:many orders", "orders many:many products"]
  }},

  "api_design": {{
    "style": "REST | GraphQL | both",
    "auth_method": "JWT | OAuth2 | Session",
    "versioning": "/api/v1/",
    "key_endpoints": ["GET /api/v1/...", "POST /api/v1/..."]
  }},

  "infrastructure": {{
    "hosting": "AWS EC2 | Railway | Render | Vercel",
    "services": ["EC2 t3.medium", "RDS PostgreSQL", "ElastiCache Redis"],
    "ci_cd": "GitHub Actions",
    "monitoring": "Sentry + CloudWatch",
    "estimated_monthly_cost_usd": 150
  }},

  "security": {{
    "auth": "JWT with refresh token rotation",
    "data_encryption": true,
    "rate_limiting": true,
    "cors": true,
    "notes": "..."
  }},

  "scalability": {{
    "current_approach": "Single server, vertical scaling",
    "scale_trigger": "When monthly active users exceed X",
    "scale_path": "Add read replicas, Redis caching, CDN"
  }},

  "risks": [
    {{"risk": "...", "mitigation": "...", "severity": "high|medium|low"}}
  ],

  "build_order": [
    {{"phase": 1, "name": "Foundation", "includes": ["Auth", "DB setup"], "weeks": 2}},
    {{"phase": 2, "name": "Core features", "includes": ["..."], "weeks": 3}},
    {{"phase": 3, "name": "Polish & deploy", "includes": ["..."], "weeks": 1}}
  ],

  "feasibility": "high | medium | low",
  "feasibility_notes": "..."
}}

Return ONLY valid JSON. Be specific and opinionated."""

EXPLANATION_PROMPT = """Based on this architecture design, write a clear 3-4 paragraph explanation for the client.

Architecture:
{architecture_json}

Requirements context:
{requirements_summary}

Write in plain English. Explain:
1. The overall approach and why it fits their needs
2. The key technology choices and why
3. How the system will be built (phases)
4. Any important trade-offs or risks they should know about

Be professional but conversational. No jargon without explanation."""


class ArchitectureAgent(BaseAgent):
    name        = "architecture"
    description = "Designs complete system architecture using Claude Sonnet"

    def run(self, conversation_history: list[dict], context: dict) -> AgentResult:
        """
        Design the complete architecture based on finalised requirements.
        Uses Claude Sonnet for the structured JSON design.
        Uses Claude again for a natural language explanation.
        """
        requirements = context.get("requirements", {})

        if not requirements:
            return AgentResult(
                agent_name = self.name,
                status     = AgentStatus.NEEDS_MORE,
                output     = {},
                message    = "I need complete requirements before designing the architecture. Let me gather a bit more information first.",
                next_agent = "requirements",
                confidence = 0.0,
            )

        # ── Step 1: Generate architecture JSON via Claude ──────────────
        logger.info("[ArchitectureAgent] Designing architecture with Claude Sonnet")

        import json
        req_json = json.dumps(requirements, indent=2)
        prompt   = ARCHITECTURE_PROMPT_TEMPLATE.format(requirements_json=req_json)

        arch_raw = self._call_claude(
            prompt     = prompt,
            system     = ARCHITECTURE_SYSTEM,
            max_tokens = 3000,
        )

        # Parse JSON from Claude response
        architecture = {}
        try:
            # Claude sometimes wraps JSON in code blocks
            clean = arch_raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            architecture = json.loads(clean.strip())
        except json.JSONDecodeError:
            logger.error(f"[ArchitectureAgent] JSON parse failed: {arch_raw[:300]}")
            # Try OpenAI as fallback for structured output
            architecture = self._call_openai(
                system     = ARCHITECTURE_SYSTEM,
                messages   = [{"role": "user", "content": prompt}],
                json_mode  = True,
                max_tokens = 2500,
            )

        # ── Step 2: Generate plain English explanation via Claude ───────
        req_summary = f"Project type: {requirements.get('project_type', 'unknown')}\n"
        req_summary += f"Features: {len(requirements.get('core_features', []))}\n"
        req_summary += f"Users: {requirements.get('expected_users', 'unknown')}"

        explanation = self._call_claude(
            prompt = EXPLANATION_PROMPT.format(
                architecture_json    = json.dumps(architecture, indent=2)[:2000],
                requirements_summary = req_summary,
            ),
            max_tokens = 600,
        )

        # ── Step 3: Compose result ─────────────────────────────────────
        message = (
            f"✅ Architecture designed!\n\n{explanation}\n\n"
            f"I'm now passing this to our feasibility and estimation agent."
        )

        return AgentResult(
            agent_name = self.name,
            status     = AgentStatus.DONE,
            output     = architecture,
            message    = message,
            next_agent = "feasibility",
            confidence = 0.92,
            metadata   = {"used_model": "claude-sonnet-4-20250514"},
        )
