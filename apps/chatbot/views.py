"""
Chatbot views — Django StreamingHttpResponse for SSE token streaming.

Endpoints:
  POST /api/chatbot/message/  → SSE stream
  POST /api/chatbot/history/  → load history
  POST /api/chatbot/reset/    → new session
  POST /api/chatbot/proposal/ → get final proposal
"""
import json
import logging
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view,permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from services.pdf_service   import generate_proposal_pdf
from services.email_service import send_proposal_email
from orchestrator.orchestrator import PipelineContext, process, stream_requirements_chat
from .models import ChatSession, ChatMessage

logger = logging.getLogger(__name__)


# ── HELPERS ───────────────────────────────────────────────────────────

def _get_or_create_session(session_id: str, conversation_id: str = None) -> ChatSession:
    if conversation_id:
        try:
            return ChatSession.objects.get(id=conversation_id)
        except ChatSession.DoesNotExist:
            pass
    session, _ = ChatSession.objects.get_or_create(session_id=session_id)
    return session


def _load_history(session: ChatSession) -> list:
    messages = list(
        session.messages
        .order_by('created_at')
        .values('role', 'content')
    )
    recent = messages[-20:] if len(messages) > 20 else messages
    return [{"role": m['role'], "content": m['content']} for m in recent]


def _save_message(session: ChatSession, role: str, content: str, agent: str = None):
    ChatMessage.objects.create(session=session, role=role, content=content, agent=agent)


def _save_context(session: ChatSession, ctx: PipelineContext):
    session.pipeline_context = ctx.to_dict()
    session.phase             = ctx.current_agent
    session.save(update_fields=['pipeline_context', 'phase', 'updated_at'])


def _load_context(session: ChatSession) -> PipelineContext:
    if session.pipeline_context:
        return PipelineContext.from_dict(session.pipeline_context)
    return PipelineContext()


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ── MAIN SSE ENDPOINT ─────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def chat_message(request):
    """
    POST /api/chatbot/message/
    Streams tokens via Server-Sent Events (SSE).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_text       = data.get('message', '').strip()
    session_id      = data.get('session_id', '')
    conversation_id = data.get('conversation_id')

    if not user_text or not session_id:
        return JsonResponse({'error': 'message and session_id required'}, status=400)

    session = _get_or_create_session(session_id, conversation_id)
    history = _load_history(session)
    ctx     = _load_context(session)

    # Save user message
    _save_message(session, 'user', user_text)
    history.append({"role": "user", "content": user_text})

    def generate():
        # ── 1. Send session metadata ───────────────────────────────────
        yield _sse({
            "event":           "meta",
            "conversation_id": str(session.id),
            "phase":           ctx.current_agent,
        })

        full_response = ""

        # ── 2. Stream conversational tokens during requirements phase ──
        if ctx.current_agent == "requirements":
            try:
                # Check if user just said "yes" to proposal
                if ctx.current_agent == "proposal" or user_text.lower().strip() in ("yes", "yes please", "generate", "generate proposal"):
                    pass  # fall through to orchestrator
                else:
                    for token in stream_requirements_chat(history):
                        full_response += token
                        yield _sse({"event": "token", "content": token})
            except Exception as e:
                logger.error(f"Stream error: {e}")

        # ── 3. Run orchestrator (extracts, advances pipeline) ──────────
        try:
            agent_message, updated_ctx, metadata = process(history, ctx,user_text)
            _save_context(session, updated_ctx)
        except Exception as e:
            logger.error(f"Orchestrator error: {e}", exc_info=True)
            agent_message = "I hit an issue — please try again."
            updated_ctx   = ctx
            metadata      = {"event": "error"}
        if metadata.get("event") == "send_email":
            try:
                proposal_text = updated_ctx.proposal.get("proposal_text", "")
                project_data  = {
                    "project_type": updated_ctx.requirements.get("project_type"),
                    "complexity":   updated_ctx.feasibility.get("complexity"),
                    "timeline":     updated_ctx.feasibility.get("timeline", {}).get("total_weeks"),
                    "cost":         updated_ctx.feasibility.get("cost_usd", {}),
                }
                pdf_bytes  = generate_proposal_pdf(proposal_text, project_data)
                email_sent = send_proposal_email(
                    to_email      = updated_ctx.user_email,
                    proposal_text = proposal_text,
                    pdf_bytes     = pdf_bytes,
                    project_data  = project_data,
                )
                yield _sse({"event": "email_sent", "success": email_sent, "email": updated_ctx.user_email})
            except Exception as e:
                logger.error(f"Email send failed: {e}")
                yield _sse({"event": "email_failed", "error": str(e)})
        # ── 4. Send agent message if different from streamed response ──
        # During requirements: we already streamed the chat response.
        # During other phases: stream the agent's output now.
        if ctx.current_agent != "requirements" or not full_response:
            for char in agent_message:
                full_response += char
                yield _sse({"event": "token", "content": char})
        elif agent_message != full_response:
            # Agent produced a different/additional message (e.g. pipeline advanced)
            suffix = agent_message
            for char in suffix:
                yield _sse({"event": "token", "content": char})
            full_response = full_response + suffix
      

        # ── 5. Save assistant response and updated context ─────────────
        _save_message(session, 'assistant', full_response or agent_message,
                      agent=updated_ctx.current_agent)
        _save_context(session, updated_ctx)

        # ── 6. Send metadata event ─────────────────────────────────────
        if metadata:
            yield _sse(metadata)

        # ── 7. Done ────────────────────────────────────────────────────
        yield _sse({
            "event":           "done",
            "conversation_id": str(session.id),
            "phase":           updated_ctx.current_agent,
            "is_complete":     updated_ctx.is_complete,
        })

    response = StreamingHttpResponse(generate(), content_type="text/event-stream")
    response['Cache-Control']     = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


# ── HISTORY ───────────────────────────────────────────────────────────
@csrf_exempt
def chat_history(request):
    """POST /api/chatbot/history/ — load conversation history."""
    session_id      = request.data.get('session_id', '')
    conversation_id = request.data.get('conversation_id')

    if not session_id:
        return Response({'error': 'session_id required'}, status=400)

    session = _get_or_create_session(session_id, conversation_id)
    ctx     = _load_context(session)

    return Response({
        'conversation_id': str(session.id),
        'phase':           session.phase,
        'messages':        _load_history(session),
        'pipeline':        ctx.to_dict(),
    })


# ── RESET ─────────────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def chat_reset(request):
    """POST /api/chatbot/reset/ — start a new conversation."""

    body=json.loads(request.body.decode('utf-8'))
    
    session_id = body["session_id"]
    if not session_id:
        return Response({'error': 'session_id required'}, status=400)

    session = ChatSession.objects.create(session_id=f"{session_id}_{ChatSession.objects.count()}")
    print(session.id)
    return Response({'conversation_id': str(session.id), 'status': 'started'})


# ── GET PROPOSAL ──────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def get_proposal(request):
    """POST /api/chatbot/proposal/ — return the generated proposal."""
    session_id      = request.data.get('session_id', '')
    conversation_id = request.data.get('conversation_id')

    if not session_id:
        return Response({'error': 'session_id required'}, status=400)

    session = _get_or_create_session(session_id, conversation_id)
    ctx     = _load_context(session)

    if not ctx.proposal:
        return Response({'error': 'Proposal not ready. Complete the conversation first.'}, status=400)

    return Response({
        'proposal_text': ctx.proposal.get('proposal_text', ''),
        'complexity':    ctx.feasibility.get('complexity'),
        'timeline':      ctx.feasibility.get('timeline', {}).get('total_weeks'),
        'cost':          ctx.feasibility.get('cost_usd', {}),
        'features':      [f.get('name') for f in ctx.requirements.get('core_features', [])],
        'modules':       ctx.requirements.get('modules', []),
    })
