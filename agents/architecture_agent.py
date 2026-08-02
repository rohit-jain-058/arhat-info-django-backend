"""
Architecture Agent — uses Claude Sonnet.
Designs full system architecture from finalised requirements.
"""
import json
import logging
# from services.ai_service import claude_json, claude_text
from prompts.prompts import (
    ARCHITECTURE_SYSTEM,
    ARCHITECTURE_USER_PROMPT,
    ARCHITECTURE_EXPLANATION_PROMPT,
)

logger = logging.getLogger(__name__)

from services.ai_service import gpt_json, gpt_text


def design(requirements: dict) -> dict:
    prompt = ARCHITECTURE_USER_PROMPT.format(
        requirements=json.dumps(requirements, indent=2)
    )
    return gpt_json(          # ← was claude_json
        system      = ARCHITECTURE_SYSTEM,
        user_prompt = prompt,
        max_tokens  = 3000,
    )


def explain(architecture: dict, requirements: dict) -> str:
    return gpt_text(          # ← was claude_text
        system      = ARCHITECTURE_SYSTEM,
        user_prompt = ARCHITECTURE_EXPLANATION_PROMPT.format(
            architecture         = json.dumps(architecture, indent=2)[:2000],
            requirements_summary = f"Type: {requirements.get('project_type')}",
        ),
        max_tokens = 600,
    )



# def design(requirements: dict) -> dict:
#     """
#     Design full architecture using Claude Sonnet.
#     Returns structured dict with stack, modules, risks, build phases.
#     """
#     prompt = ARCHITECTURE_USER_PROMPT.format(
#         requirements=json.dumps(requirements, indent=2)
#     )
#     architecture = claude_json(
#         system      = ARCHITECTURE_SYSTEM,
#         user_prompt = prompt,
#         max_tokens  = 3000,
#     )
#     return architecture


# def explain(architecture: dict, requirements: dict) -> str:
#     """
#     Generate a plain-English explanation of the architecture for the user.
#     """
#     req_summary = (
#         f"Project type: {requirements.get('project_type', 'unknown')}\n"
#         f"Features: {len(requirements.get('core_features', []))}\n"
#         f"Users: {requirements.get('expected_users', 'unknown')}"
#     )

#     return claude_text(
#         system      = ARCHITECTURE_SYSTEM,
#         user_prompt = ARCHITECTURE_EXPLANATION_PROMPT.format(
#             architecture        = json.dumps(architecture, indent=2)[:2000],
#             requirements_summary= req_summary,
#         ),
#         max_tokens = 600,
#     )
