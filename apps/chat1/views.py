"""
Chat views — Django StreamingHttpResponse for SSE token streaming.

Endpoints:
  POST /api/chat/message/   → SSE streaming chat
  POST /api/chat/history/   → load conversation history
  POST /api/chat/reset/     → start new conversation
  POST /api/chat/analyze/   → full project analysis
  POST /api/chat/proposal/  → generate proposal (Anthropic)
"""
import json
import logging
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from rest_framework.decorators import api_view
from rest_framework.response import Response

from services.ai_service import (
    stream_chat_response,
    detect_intent,
    extract_requirements,
    suggest_architecture,
    estimate_project,
    get_clarifying_question,
    should_escalate,
    generate_proposal,
    detect_phase,
)
from services.memory_service import (
    get_or_create_user,
    get_or_create_conversation,
    save_message,
    load_conversation_history,
    get_or_create_project,
    update_project_analysis,
    escalate_conversation,
)

logger = logging.getLogger(__name__)

# Extract requirements every N user messages
EXTRACT_EVERY_N = 3


# ── STREAMING CHAT ────────────────────────────────────────────────────
@csrf_exempt
def chat_message(request):
    """
    Main SSE streaming endpoint.
    Streams response token by token using Django StreamingHttpResponse.
    Also sends structured metadata events between tokens.
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

    # Load history before saving new message
    history = load_conversation_history(conv)
    is_first = len(history) == 0

    # Save user message
    save_message(conv, 'user', user_text)

    # Add to history for this response
    history.append({"role": "user", "content": user_text})

    # ── Intent detection on first message ─────────────────────────────
    intent_data = {}
    if is_first:
        intent_data = detect_intent(user_text)
        conv.intent = intent_data.get('intent', 'other')
        conv.save(update_fields=['intent'])

    def generate():
        full_response = ""
        conv_id_str   = str(conv.id)

        # ── Meta event ────────────────────────────────────────────────
        meta = json.dumps({
            "event":           "meta",
            "conversation_id": conv_id_str,
            "phase":           conv.phase,
            "intent":          intent_data.get("intent", conv.intent or ""),
        })
        yield f"data: {meta}\n\n"

        # ── Escalation check every 5 messages ─────────────────────────
        if len(history) > 4 and len(history) % 5 == 0:
            escalation = should_escalate(history)
            if escalation.get("should_escalate"):
                esc = json.dumps({
                    "event":  "escalate",
                    "reason": escalation.get("reason", ""),
                })
                yield f"data: {esc}\n\n"
                escalate_conversation(conv)

        # ── Stream AI response token by token ─────────────────────────
        for token in stream_chat_response(history):
            full_response += token
            payload = json.dumps({"event": "token", "content": token})
            yield f"data: {payload}\n\n"

        # ── Save assistant response ────────────────────────────────────
        asst_msg = save_message(conv, 'assistant', full_response)

        # ── Extract requirements every N messages ──────────────────────
        updated_history = history + [{"role": "assistant", "content": full_response}]
        if len(updated_history) % EXTRACT_EVERY_N == 0 and len(updated_history) >= 3:
            try:
                requirements = extract_requirements(updated_history)
                new_phase    = detect_phase(len(updated_history), requirements)

                conv.phase = new_phase
                conv.save(update_fields=['phase'])

                project = get_or_create_project(conv)
                update_project_analysis(project, requirements)

                # Send requirements event to frontend
                req_event = json.dumps({
                    "event":         "requirements",
                    "data":          requirements,
                    "phase":         new_phase,
                    "missing_count": len(requirements.get("missing_info", [])),
                })
                yield f"data: {req_event}\n\n"
            except Exception as e:
                logger.error(f"Requirement extraction failed: {e}")

        # ── Done event ─────────────────────────────────────────────────
        done = json.dumps({"event": "done", "conversation_id": conv_id_str})
        yield f"data: {done}\n\n"

    response = StreamingHttpResponse(generate(), content_type="text/event-stream")
    response['Cache-Control']       = 'no-cache'
    response['X-Accel-Buffering']   = 'no'
    response['Access-Control-Allow-Origin'] = '*'
    return response


# ── CONVERSATION HISTORY ──────────────────────────────────────────────
@api_view(['POST'])
def chat_history(request):
    session_id      = request.data.get('session_id', '')
    conversation_id = request.data.get('conversation_id')

    if not session_id:
        return Response({'error': 'session_id required'}, status=400)

    user    = get_or_create_user(session_id)
    conv    = get_or_create_conversation(user, conversation_id)
    history = load_conversation_history(conv)

    return Response({
        'conversation_id': str(conv.id),
        'phase':           conv.phase,
        'intent':          conv.intent,
        'messages':        history,
    })


# ── RESET CONVERSATION ────────────────────────────────────────────────
@api_view(['POST'])
def chat_reset(request):
    session_id = request.data.get('session_id', '')
    if not session_id:
        return Response({'error': 'session_id required'}, status=400)

    from apps.chat.models import Conversation as ConvModel
    user = get_or_create_user(session_id)
    conv = ConvModel.objects.create(user=user)
    return Response({'conversation_id': str(conv.id), 'status': 'started'})


# ── FULL PROJECT ANALYSIS ─────────────────────────────────────────────
@api_view(['POST'])
def analyze_project(request):
    """
    Run full analysis pipeline:
    1. Extract structured requirements
    2. Suggest architecture
    3. Estimate timeline + cost
    4. Identify missing information
    5. Generate next clarifying question
    """
    session_id      = request.data.get('session_id', '')
    conversation_id = request.data.get('conversation_id')

    if not session_id or not conversation_id:
        return Response({'error': 'session_id and conversation_id required'}, status=400)

    user    = get_or_create_user(session_id)
    conv    = get_or_create_conversation(user, conversation_id)
    history = load_conversation_history(conv)

    if len(history) < 2:
        return Response({'error': 'Not enough conversation history to analyze'}, status=400)

    # Run pipeline
    requirements   = extract_requirements(history)
    architecture   = suggest_architecture(requirements)
    estimation     = estimate_project(requirements, architecture)
    next_question  = None

    if requirements.get("missing_info"):
        next_question = get_clarifying_question(history, requirements)

    # Save to DB
    project = get_or_create_project(conv)
    update_project_analysis(project, requirements, architecture, estimation)

    return Response({
        'project_id':         str(project.id),
        'requirements':       requirements,
        'architecture':       architecture,
        'estimation':         estimation,
        'next_question':      next_question,
        'phase':              conv.phase,
        'ready_for_proposal': len(requirements.get("missing_info", [])) <= 1,
    })


# ── GENERATE PROPOSAL ─────────────────────────────────────────────────
@api_view(['POST'])
def generate_project_proposal(request):
    """Generate a client-facing proposal using Anthropic Claude."""
    session_id      = request.data.get('session_id', '')
    conversation_id = request.data.get('conversation_id')

    if not session_id or not conversation_id:
        return Response({'error': 'session_id and conversation_id required'}, status=400)

    user = get_or_create_user(session_id)
    conv = get_or_create_conversation(user, conversation_id)

    try:
        project  = conv.project
        analysis = project.analysis
    except Exception:
        return Response({'error': 'No project found. Run /api/chat/analyze/ first.'}, status=400)

    proposal = generate_proposal(
        requirements = analysis.structured_reqs or {},
        architecture = analysis.architecture    or {},
        estimation   = {
            'complexity':     project.complexity,
            'timeline_weeks': project.timeline_weeks,
            'cost_usd':       project.estimated_cost,
        },
    )

    # Save proposal text
    analysis.proposal_text = proposal
    analysis.save(update_fields=['proposal_text'])

    return Response({
        'project_id': str(project.id),
        'proposal':   proposal,
        'complexity': project.complexity,
        'timeline':   project.timeline_weeks,
        'cost':       project.estimated_cost,
        'features':   project.features,
        'modules':    project.modules,
    })
