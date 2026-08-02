"""
Chat views — Django StreamingHttpResponse + Agent Orchestrator.

The key difference from the old chatbot:
- Every message goes through the Orchestrator
- Orchestrator decides which agent runs
- Agents signal DONE to advance the pipeline
- Requirements → Architecture → Feasibility → Proposal is automatic
"""
import json
import logging
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response

from orchestrator.orchestrator import Orchestrator, PipelineContext
from services.memory_service import (
    get_or_create_user,
    get_or_create_conversation,
    save_message,
    load_conversation_history,
    save_pipeline_context,
    load_pipeline_context,
)

logger = logging.getLogger(__name__)

# Single orchestrator instance (shared across requests)
_orchestrator = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


# ── MAIN STREAMING ENDPOINT ───────────────────────────────────────────
@csrf_exempt
def chat_message(request):
    """
    SSE streaming endpoint.
    Streams tokens + agent metadata events to the frontend.
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

    # ── Load state ────────────────────────────────────────────────────
    user = get_or_create_user(session_id)
    conv = get_or_create_conversation(user, conversation_id)

    history         = load_conversation_history(conv)
    pipeline_ctx    = load_pipeline_context(conv)

    # Save user message
    save_message(conv, 'user', user_text)
    history.append({"role": "user", "content": user_text})

    def generate():
        orchestrator = get_orchestrator()

        # ── Meta event: tell frontend current phase ────────────────────
        meta = json.dumps({
            "event":           "meta",
            "conversation_id": str(conv.id),
            "phase":           pipeline_ctx.current_agent,
            "is_complete":     pipeline_ctx.is_complete,
        })
        yield f"data: {meta}\n\n"

        # ── Stream conversational response during requirements phase ────
        # This gives immediate token-by-token feedback while agents process
        full_response = ""

        if pipeline_ctx.current_agent == "requirements" and not pipeline_ctx.is_complete:
            # Stream a warm conversational reply first
            try:
                for token in orchestrator.stream_requirements_response(history):
                    full_response += token
                    yield f"data: {json.dumps({'event':'token','content':token})}\n\n"
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                full_response = "Let me think about that..."
                yield f"data: {json.dumps({'event':'token','content':full_response})}\n\n"
        else:
            # For non-requirements phases, show a thinking indicator
            thinking = json.dumps({"event": "thinking", "agent": pipeline_ctx.current_agent})
            yield f"data: {thinking}\n\n"

        # ── Run the orchestrator (agent pipeline) ──────────────────────
        try:
            agent_response, updated_ctx, metadata = orchestrator.process_message(
                user_message         = user_text,
                conversation_history = history,
                pipeline_context     = pipeline_ctx,
            )
        except Exception as e:
            logger.error(f"Orchestrator error: {e}", exc_info=True)
            agent_response = "I hit an issue — please try again."
            updated_ctx    = pipeline_ctx
            metadata       = {"event": "error"}

        # ── If requirements phase: agent_response contains the question
        # If further phases: agent_response is the architecture/proposal text
        # Stream the agent response if it wasn't already streamed
        if pipeline_ctx.current_agent != "requirements" or updated_ctx.current_agent != "requirements":
            # New content from agent — stream it
            for char in agent_response:
                yield f"data: {json.dumps({'event':'token','content':char})}\n\n"
            final_text = agent_response
        else:
            # Requirements phase: we already streamed full_response
            # The agent_response is the clarifying question — only send if different
            if agent_response != full_response and full_response:
                final_text = full_response
            else:
                final_text = agent_response

        # ── Save assistant message ─────────────────────────────────────
        save_message(conv, 'assistant', final_text,
                     structured_data=metadata.get("requirements"))
        save_pipeline_context(conv, updated_ctx)

        # Update conversation phase
        conv.phase = updated_ctx.current_agent
        conv.save(update_fields=['phase'])

        # ── Send structured data events ────────────────────────────────
        if metadata:
            yield f"data: {json.dumps(metadata)}\n\n"

        # ── Done ───────────────────────────────────────────────────────
        done = json.dumps({
            "event":           "done",
            "conversation_id": str(conv.id),
            "phase":           updated_ctx.current_agent,
            "is_complete":     updated_ctx.is_complete,
        })
        yield f"data: {done}\n\n"

    response = StreamingHttpResponse(generate(), content_type="text/event-stream")
    response['Cache-Control']     = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


# ── CONVERSATION HISTORY ──────────────────────────────────────────────
@api_view(['POST'])
@csrf_exempt
def chat_history(request):
    session_id      = request.data.get('session_id', '')
    conversation_id = request.data.get('conversation_id')
    if not session_id:
        return Response({'error': 'session_id required'}, status=400)

    user    = get_or_create_user(session_id)
    conv    = get_or_create_conversation(user, conversation_id)
    history = load_conversation_history(conv)
    ctx     = load_pipeline_context(conv)

    return Response({
        'conversation_id': str(conv.id),
        'phase':           conv.phase,
        'messages':        history,
        'pipeline':        ctx.to_dict(),
    })


# ── RESET ──────────────────────────────────────────────────────────────
@api_view(['POST'])
@csrf_exempt
def chat_reset(request):
    session_id = request.data.get('session_id', '')
    if not session_id:
        return Response({'error': 'session_id required'}, status=400)

    from apps.chat.models import Conversation
    user = get_or_create_user(session_id)
    conv = Conversation.objects.create(user=user)
    return Response({'conversation_id': str(conv.id), 'status': 'started'})


# ── GET PROPOSAL ───────────────────────────────────────────────────────
@api_view(['POST'])
@csrf_exempt
def get_proposal(request):
    """Return the full proposal and SOW for a completed conversation."""
    session_id      = request.data.get('session_id', '')
    conversation_id = request.data.get('conversation_id')
    if not session_id or not conversation_id:
        return Response({'error': 'session_id and conversation_id required'}, status=400)

    user = get_or_create_user(session_id)
    conv = get_or_create_conversation(user, conversation_id)
    ctx  = load_pipeline_context(conv)

    if not ctx.proposal:
        return Response({'error': 'Proposal not ready yet'}, status=400)

    return Response({
        'proposal_text': ctx.proposal.get('proposal_text'),
        'sow_text':      ctx.proposal.get('sow_text'),
        'complexity':    ctx.proposal.get('complexity'),
        'timeline':      ctx.proposal.get('timeline_weeks'),
        'cost_min':      ctx.proposal.get('cost_min'),
        'cost_max':      ctx.proposal.get('cost_max'),
        'features':      ctx.proposal.get('features', []),
        'modules':       ctx.proposal.get('modules', []),
    })
