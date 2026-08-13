"""
Proposal Agent — Anthropic Claude Sonnet
Responsibility: Generate a complete, professional client-facing proposal and
Statement of Work (SOW) using all gathered context.
This is the final agent in the pipeline.
"""
import json
import logging
from .base_agent import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

PROPOSAL_SYSTEM = """You are a senior technical account manager at Tylented writing a client proposal.
Write clearly, professionally, and warmly. No jargon without explanation.
This proposal will be sent directly to the client."""

PROPOSAL_PROMPT_TEMPLATE = """Write a complete project proposal for this client.

Requirements:
{requirements}

Architecture:
{architecture}

Feasibility & Estimation:
{feasibility}

Format the proposal exactly like this:

---
# Project Proposal — [Project Name]
**Prepared by:** Tylented Engineering
**Date:** [Today's date]

## Executive Summary
[2-3 sentences. What we'll build, the business value, and our recommended approach.]

## Understanding Your Requirements
[What we understood about their business problem and goals. Reference specific things they said.]

## Proposed Solution
[What we will build and why this approach. 2-3 paragraphs.]

## System Architecture
[Plain-English explanation of the architecture. Mention key technologies and why chosen.]

## Project Modules
[List each module with a 1-sentence description]
- **Module name:** Description
...

## Build Timeline
[Phase-by-phase timeline with weeks]
| Phase | What's included | Duration |
|-------|----------------|----------|
| Phase 1: Foundation | ... | X weeks |
...
**Total: X weeks**

## Investment
| Item | Cost |
|------|------|
| ... | $X,XXX |
| **Total** | **$X,XXX – $X,XXX** |

*Monthly infrastructure: ~$XXX/month*

## Recommended First Step
[Prototype recommendation or direct build — explain why]

## Why Tylented
[2-3 sentences. Relevant experience, Python/Django expertise, AI engineering.]

## Next Steps
1. Review this proposal
2. [Specific next action]
3. [Kick-off step]

---

Write in a professional but warm tone. Use the actual project details from the requirements.
Do NOT use placeholder text."""


SOW_PROMPT_TEMPLATE = """Write a concise Statement of Work (SOW) based on this proposal context.

Requirements: {requirements_brief}
Architecture: {architecture_brief}
Estimation:   {estimation_brief}

Include:
1. Scope of Work (what IS included)
2. Out of Scope (what is NOT included — prevents scope creep)
3. Deliverables (specific items client receives)
4. Acceptance Criteria (how we know it's done)
5. Client Responsibilities (what client must provide)
6. Payment Schedule (milestone-based)
7. Change Request Process (1 paragraph)

Keep it clear and professional. This is a legal-adjacent document."""


class ProposalAgent(BaseAgent):
    name        = "proposal"
    description = "Generates professional proposal and SOW using Claude Sonnet"

    def run(self, conversation_history: list[dict], context: dict) -> AgentResult:
        requirements = context.get("requirements", {})
        architecture = context.get("architecture", {})
        feasibility  = context.get("feasibility",  {})

        if not feasibility:
            return AgentResult(
                agent_name = self.name,
                status     = AgentStatus.NEEDS_MORE,
                output     = {},
                message    = "Need feasibility assessment first.",
                next_agent = "feasibility",
                confidence = 0.0,
            )

        # ── Generate main proposal ─────────────────────────────────────
        logger.info("[ProposalAgent] Generating proposal with Claude Sonnet")

        def safe_json(obj, limit=1200):
            return json.dumps(obj, indent=2)[:limit] if obj else "{}"

        proposal_text = self._call_claude(
            system = PROPOSAL_SYSTEM,
            prompt = PROPOSAL_PROMPT_TEMPLATE.format(
                requirements = safe_json(requirements),
                architecture = safe_json(architecture),
                feasibility  = safe_json(feasibility),
            ),
            max_tokens = 2500,
        )

        # ── Generate SOW ───────────────────────────────────────────────
        timeline  = feasibility.get("timeline", {})
        cost      = feasibility.get("cost_usd", {})
        features  = [f.get("name","") for f in requirements.get("core_features",[])[:5]]

        sow_text = self._call_claude(
            system = PROPOSAL_SYSTEM,
            prompt = SOW_PROMPT_TEMPLATE.format(
                requirements_brief = f"Project: {requirements.get('project_type')}. Features: {', '.join(features)}",
                architecture_brief = f"Stack: {architecture.get('tech_stack', {}).get('backend', {}).get('technology','Django')} + {architecture.get('tech_stack', {}).get('frontend', {}).get('technology','React')}. Pattern: {architecture.get('architecture_pattern','Monolith')}",
                estimation_brief   = f"Timeline: {timeline.get('total_weeks','?')} weeks. Budget: ${cost.get('min','?')}-${cost.get('max','?')}",
            ),
            max_tokens = 1500,
        )

        output = {
            "proposal_text":   proposal_text,
            "sow_text":        sow_text,
            "project_type":    requirements.get("project_type"),
            "complexity":      feasibility.get("complexity"),
            "timeline_weeks":  timeline.get("total_weeks"),
            "cost_min":        cost.get("min"),
            "cost_max":        cost.get("max"),
            "features":        features,
            "modules":         requirements.get("modules", []),
            "prototype_cost":  feasibility.get("prototype_recommendation", {}).get("cost_usd"),
        }

        message = (
            "📄 Your proposal is ready!\n\n"
            "I've prepared:\n"
            "✓ Full project proposal with architecture and timeline\n"
            "✓ Statement of Work (SOW)\n"
            "✓ Cost breakdown\n\n"
            "Would you like to book a call to walk through this together, or shall I send the proposal directly?"
        )

        return AgentResult(
            agent_name = self.name,
            status     = AgentStatus.DONE,
            output     = output,
            message    = message,
            next_agent = None,   # end of pipeline
            confidence = 0.95,
            metadata   = {"used_model": "claude-sonnet-4-20250514"},
        )
