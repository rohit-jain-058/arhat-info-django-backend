"""
Proposal Agent — uses Claude Sonnet.
Writes a professional client-facing proposal and SOW.
"""
import json
import logging
from services.ai_service import claude_text
from prompts.prompts import PROPOSAL_SYSTEM, PROPOSAL_USER_PROMPT

logger = logging.getLogger(__name__)
from services.ai_service import gpt_text


def generate(requirements: dict, architecture: dict, feasibility: dict) -> str:
    return gpt_text(          # ← was claude_text
        system      = PROPOSAL_SYSTEM,
        user_prompt = PROPOSAL_USER_PROMPT.format(
            requirements = json.dumps(requirements, indent=2)[:1500],
            architecture = json.dumps(architecture, indent=2)[:1500],
            estimation   = json.dumps(feasibility,  indent=2)[:800],
            project_type = requirements.get("project_type", "Project").replace("_", " ").title(),
        ),
        max_tokens = 2500,
    )