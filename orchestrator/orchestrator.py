"""
Orchestrator — routes messages between agents.

Pipeline:
  requirements → architecture → feasibility → proposal

Each stage runs automatically when the previous one signals done.
Context is persisted in PostgreSQL between messages via pipeline_context JSON field.
"""
import logging
from dataclasses import dataclass, field

import agents.requirements_agent as req_agent
import agents.architecture_agent as arch_agent
import agents.feasibility_agent  as feas_agent
import agents.proposal_agent     as prop_agent

logger = logging.getLogger(__name__)


# ── Pipeline context — persisted per conversation ─────────────────────
@dataclass
class PipelineContext:
    current_agent: str  = "requirements"
    requirements:  dict = field(default_factory=dict)
    architecture:  dict = field(default_factory=dict)
    feasibility:   dict = field(default_factory=dict)
    proposal:      dict = field(default_factory=dict)
    user_email:    str  = ""
    is_complete:   bool = False
    is_escalated:  bool = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineContext":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


# ── Main orchestrator function ─────────────────────────────────────────
def process(history: list, ctx: PipelineContext,user_message: str = "") -> tuple[str, PipelineContext, dict]:
    """
    Process one turn of conversation.

    Args:
        history: full conversation in OpenAI format [{"role":..,"content":..}]
        ctx:     current pipeline context (loaded from DB)

    Returns:
        (message_to_show_user, updated_ctx, metadata_for_frontend)
    """
    phase = ctx.current_agent

    # ── Requirements phase ────────────────────────────────────────────
    if phase == "requirements":
        requirements = req_agent.extract(history)
        ctx.requirements = requirements

        user_count = len([m for m in history if m["role"] == "user"])
        logger.info(
            f"[Requirements] user_messages={user_count} "
            f"score={requirements.get('completeness_score')} "
            f"ready={requirements.get('ready_for_architecture')}"
        )

        # Ask the bot what to do next
        message, is_done = req_agent.next_question(history, requirements)

        if is_done:
            logger.info("[Orchestrator] Bot says done — advancing pipeline")
            # Send closing message first, then advance
            closing = message  # warm closing from the bot
            pipeline_msg, ctx, meta = _advance_pipeline(ctx, history)
            # Prepend closing to the pipeline message
            full_message = closing + "\n\n" + pipeline_msg
            return full_message, ctx, meta

        # Bot wants to ask another question
        meta = {
            "event":        "requirements_update",
            "phase":        "requirements",
            "completeness": requirements.get("completeness_score", 0),
            "requirements": requirements,
        }
        return message, ctx, meta
    # ── If somehow landed on a later phase with missing context ───────
    elif phase == "architecture" and not ctx.requirements:
        return "Let me gather a bit more information first.", ctx, {"phase": "requirements"}

    elif phase == "proposal":
        confirmed_words = ("yes", "yes please", "generate", "generate proposal",
                    "go ahead", "proceed", "sure", "ok", "okay", "yep", "yeah")
        if user_message.lower().strip() not in confirmed_words:
            return (
                "Would you like me to generate your full project proposal? Type **yes** to proceed.",
                ctx,
                {"event": "awaiting_confirmation", "phase": "proposal"}
            )

        proposal_text = prop_agent.generate(
            requirements = ctx.requirements,
            architecture = ctx.architecture,
            feasibility  = ctx.feasibility,
        )
        ctx.proposal      = {"proposal_text": proposal_text}
        ctx.current_agent = "email_collection"     # ← move to email phase, not complete

        meta = {
            "event":    "proposal_ready",
            "phase":    "email_collection",
            "proposal": ctx.proposal,
        }
        return (
            "📄 Your proposal is ready!\n\n"
            "I can send you the full proposal as a **PDF to your email for further communication**.\n\n"
            "**What is your email address?** (or type **skip** to finish without sending)",
            ctx,
            meta,
        )

    # ── Email collection phase ────────────────────────────────────────
    elif phase == "email_collection":
        msg = user_message.strip().lower()

        # User wants to skip
        if msg in ("skip", "no", "no thanks", "nope", "don't send", "dont send"):
            ctx.current_agent = "complete"
            ctx.is_complete   = True
            return (
                "No problem! You can download the proposal from the chat. "
                "Feel free to reach out at hello@arhatinfo.com anytime. 🚀",
                ctx,
                {"event": "complete", "phase": "complete"},
            )

        # Validate email — simple check
        import re
        email_pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, user_message.strip()):
            return (
                "That doesn't look like a valid email address. "
                "Please enter a valid email (e.g. name@company.com) or type **skip**.",
                ctx,
                {"event": "awaiting_email", "phase": "email_collection"},
            )

        # Valid email — save it and trigger send
        ctx.user_email    = user_message.strip()
        ctx.current_agent = "complete"
        ctx.is_complete   = True

        meta = {
            "event":      "send_email",
            "email":      ctx.user_email,
            "phase":      "complete",
            "proposal":   ctx.proposal,
            "feasibility": ctx.feasibility,
            "requirements": ctx.requirements,
        }
        return (
            f"✅ Sending your proposal to **{ctx.user_email}** now...\n\n"
            f"You'll receive it within a minute. "
            f"If you have any questions reply here or email hello@arhatinfo.com 🚀",
            ctx,
            meta,
        )
    return "Something went wrong — please try again.", ctx, {"event": "error"}


def stream_requirements_chat(history: list):
    """
    Stream a conversational response during requirements gathering.
    This is what the user sees in real-time as they chat.
    """
    return req_agent.stream_question(history)


# ── Internal: auto-advance requirements → arch → feasibility ──────────
def _advance_pipeline(ctx: PipelineContext, history: list) -> tuple:
    messages = []

    # Smooth transition — acknowledge the conversation before jumping
    messages.append(
        "Thanks — I now have a clear picture of what you need. "
        "Let me design the architecture and put together an estimate for you.\n\n"
        "⏳ This will take a moment...\n\n"
    )

    # Step 1: Architecture
    ctx.current_agent = "architecture"
    logger.info("[Orchestrator] Running Architecture Agent")
    architecture = arch_agent.design(ctx.requirements)
    explanation  = arch_agent.explain(architecture, ctx.requirements)
    ctx.architecture = architecture
    messages.append(f"🏗️ **Architecture designed:**\n\n{explanation}\n\n")

    # Step 2: Feasibility
    ctx.current_agent = "feasibility"
    logger.info("[Orchestrator] Running Feasibility Agent")
    feasibility = feas_agent.estimate(ctx.requirements, ctx.architecture)
    summary     = feas_agent.build_summary_message(feasibility)
    ctx.feasibility = feasibility
    messages.append(f"---\n\n📊 **Feasibility & Estimate:**\n\n{summary}\n\n")

    # Step 3: Ask for proposal confirmation
    ctx.current_agent = "proposal"
    messages.append(
        "---\n\n"
        "I'm ready to write your full project proposal.\n\n"
        "It will include the full architecture, timeline, cost breakdown, "
        "modules, and a Statement of Work.\n\n"
        "**Shall I generate it? Type yes to proceed.**"
    )

    combined = "".join(messages)
    meta = {
        "event":        "pipeline_advanced",
        "phase":        "proposal",
        "requirements": ctx.requirements,
        "architecture": ctx.architecture,
        "feasibility":  ctx.feasibility,
    }
    return combined, ctx, meta