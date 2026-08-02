"""
Memory service — saves/loads conversation history and pipeline context.
"""
import logging
from apps.chat.models import ChatUser, Conversation, Message
from orchestrator.orchestrator import PipelineContext

logger = logging.getLogger(__name__)


def get_or_create_user(session_id: str) -> ChatUser:
    user, _ = ChatUser.objects.get_or_create(session_id=session_id)
    return user


def get_or_create_conversation(user: ChatUser, conversation_id: str | None) -> Conversation:
    if conversation_id:
        try:
            return Conversation.objects.get(id=conversation_id, user=user)
        except (Conversation.DoesNotExist, Exception):
            pass
    return Conversation.objects.create(user=user)


def save_message(conversation: Conversation, role: str, content: str,
                 structured_data: dict | None = None, agent_name: str | None = None) -> Message:
    return Message.objects.create(
        conversation    = conversation,
        role            = role,
        content         = content,
        structured_data = structured_data,
        agent_name      = agent_name,
    )


def load_conversation_history(conversation: Conversation) -> list:
    """Return last 20 messages in OpenAI format."""
    messages = list(
        conversation.messages
        .order_by('created_at')
        .values('role', 'content')
    )
    recent = messages[-20:] if len(messages) > 20 else messages
    return [{"role": m['role'], "content": m['content']} for m in recent]


def save_pipeline_context(conversation: Conversation, ctx: PipelineContext) -> None:
    """Persist the full pipeline context (requirements, architecture, etc.) to DB."""
    conversation.pipeline_context = ctx.to_dict()
    conversation.phase            = ctx.current_agent if not ctx.is_complete else 'complete'
    conversation.save(update_fields=['pipeline_context', 'phase', 'updated_at'])


def load_pipeline_context(conversation: Conversation) -> PipelineContext:
    """Load pipeline context from DB or return fresh one."""
    stored = conversation.pipeline_context
    if stored:
        return PipelineContext.from_dict(stored)
    return PipelineContext()
