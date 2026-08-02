"""
AI tool views — all powered by GPT-4o via gpt_service.py.

Endpoints:
  POST /api/tools/ai/prompt/
  POST /api/tools/ai/email/
  POST /api/tools/ai/linkedin/
  POST /api/tools/ai/cover-letter/
  POST /api/tools/ai/resume-summary/
  POST /api/tools/ai/sql/
  POST /api/tools/ai/regex/
  POST /api/tools/ai/api-docs/
  POST /api/tools/ai/meeting-notes/
"""
import logging
import time

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..models import AIToolRequest
from apps.subscriptions.permissions import IsAIToolsSubscriber
from ..gpt_service import (
    generate_prompt, generate_email, generate_linkedin_post,
    generate_cover_letter, generate_resume_summary, generate_sql,
    generate_regex, generate_api_docs, generate_meeting_notes,
)

logger = logging.getLogger(__name__)


def _get_ip(request) -> str:
    for h in ['HTTP_CF_CONNECTING_IP', 'HTTP_X_REAL_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR']:
        v = request.META.get(h, '').split(',')[0].strip()
        if v: return v
    return ''


def _log(tool, request, result: dict, input_data: dict):
    try:
        AIToolRequest.objects.create(
            tool              = tool,
            ip_address        = _get_ip(request),
            user_agent        = request.META.get('HTTP_USER_AGENT', '')[:512],
            prompt_tokens     = result.get('prompt_tokens'),
            completion_tokens = result.get('completion_tokens'),
            total_tokens      = result.get('total_tokens'),
            model_used        = result.get('model', 'gpt-4o'),
            duration_ms       = result.get('duration_ms'),
            input_data        = input_data,
            output_preview    = result.get('text', '')[:500],
            success           = True,
        )
    except Exception as e:
        logger.warning(f'AI log failed: {e}')


def _log_error(tool, request, error: str, input_data: dict = None):
    try:
        AIToolRequest.objects.create(
            tool       = tool,
            ip_address = _get_ip(request),
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:512],
            success    = False,
            error      = error,
            input_data = input_data,
        )
    except Exception as e:
        logger.warning(f'AI error log failed: {e}')


# ── PROMPT GENERATOR ───────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
def prompt_generator(request):
    goal    = request.data.get('goal', '').strip()
    context = request.data.get('context', '')
    fmt     = request.data.get('format', 'detailed')

    if not goal:
        return Response({'error': 'goal is required'}, status=400)

    inputs = {'goal': goal, 'context': context, 'format': fmt}
    try:
        result = generate_prompt(goal, context, fmt)
        _log('prompt_gen', request, result, inputs)
        return Response({'text': result['text'], 'tokens': result['total_tokens']})
    except Exception as e:
        _log_error('prompt_gen', request, str(e), inputs)
        return Response({'error': str(e)}, status=500)


# ── EMAIL GENERATOR ────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
def email_generator(request):
    purpose   = request.data.get('purpose', 'follow-up')
    recipient = request.data.get('recipient', '')
    context   = request.data.get('context', '').strip()
    tone      = request.data.get('tone', 'professional')

    inputs = {'purpose': purpose, 'recipient': recipient, 'context': context, 'tone': tone}
    try:
        result = generate_email(purpose, recipient, context, tone)
        _log('email_gen', request, result, inputs)
        return Response({'text': result['text'], 'tokens': result['total_tokens']})
    except Exception as e:
        _log_error('email_gen', request, str(e), inputs)
        return Response({'error': str(e)}, status=500)


# ── LINKEDIN POST GENERATOR ────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
def linkedin_generator(request):
    topic = request.data.get('topic', '').strip()
    hook  = request.data.get('hook', '')
    style = request.data.get('style', 'thought-leadership')

    if not topic:
        return Response({'error': 'topic is required'}, status=400)

    inputs = {'topic': topic, 'hook': hook, 'style': style}
    try:
        result = generate_linkedin_post(topic, hook, style)
        _log('linkedin_post', request, result, inputs)
        return Response({'text': result['text'], 'tokens': result['total_tokens']})
    except Exception as e:
        _log_error('linkedin_post', request, str(e), inputs)
        return Response({'error': str(e)}, status=500)


# ── COVER LETTER GENERATOR ─────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
def cover_letter_generator(request):
    role        = request.data.get('role', '').strip()
    company     = request.data.get('company', '')
    skills      = request.data.get('skills', '')
    achievement = request.data.get('achievement', '')

    if not role:
        return Response({'error': 'role is required'}, status=400)

    inputs = {'role': role, 'company': company, 'skills': skills, 'achievement': achievement}
    try:
        result = generate_cover_letter(role, company, skills, achievement)
        _log('cover_letter', request, result, inputs)
        return Response({'text': result['text'], 'tokens': result['total_tokens']})
    except Exception as e:
        _log_error('cover_letter', request, str(e), inputs)
        return Response({'error': str(e)}, status=500)


# ── RESUME SUMMARY GENERATOR ───────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
def resume_summary_generator(request):
    role   = request.data.get('role', '').strip()
    years  = request.data.get('years', '')
    skills = request.data.get('skills', '')
    goal   = request.data.get('goal', '')

    if not role:
        return Response({'error': 'role is required'}, status=400)

    inputs = {'role': role, 'years': years, 'skills': skills, 'goal': goal}
    try:
        result = generate_resume_summary(role, years, skills, goal)
        _log('resume_summary', request, result, inputs)
        return Response({'text': result['text'], 'tokens': result['total_tokens']})
    except Exception as e:
        _log_error('resume_summary', request, str(e), inputs)
        return Response({'error': str(e)}, status=500)


# ── SQL GENERATOR ──────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
def sql_generator(request):
    question = request.data.get('question', '').strip()
    schema   = request.data.get('schema', '')
    dialect  = request.data.get('dialect', 'PostgreSQL')

    if not question:
        return Response({'error': 'question is required'}, status=400)

    inputs = {'question': question, 'schema': schema, 'dialect': dialect}
    try:
        result = generate_sql(question, schema, dialect)
        _log('sql_gen', request, result, inputs)
        return Response({'text': result['text'], 'tokens': result['total_tokens']})
    except Exception as e:
        _log_error('sql_gen', request, str(e), inputs)
        return Response({'error': str(e)}, status=500)


# ── REGEX GENERATOR ────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
def regex_generator(request):
    description = request.data.get('description', '').strip()
    example     = request.data.get('example', '')
    language    = request.data.get('language', 'JavaScript')

    if not description:
        return Response({'error': 'description is required'}, status=400)

    inputs = {'description': description, 'example': example, 'language': language}
    try:
        result = generate_regex(description, example, language)
        _log('regex_gen', request, result, inputs)
        return Response({'text': result['text'], 'tokens': result['total_tokens']})
    except Exception as e:
        _log_error('regex_gen', request, str(e), inputs)
        return Response({'error': str(e)}, status=500)


# ── API DOCS GENERATOR ─────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
def api_docs_generator(request):
    endpoint = request.data.get('endpoint', '').strip()
    fmt      = request.data.get('format', 'Markdown')

    if not endpoint:
        return Response({'error': 'endpoint is required'}, status=400)

    inputs = {'endpoint': endpoint[:2000], 'format': fmt}
    try:
        result = generate_api_docs(endpoint, fmt)
        _log('api_docs', request, result, inputs)
        return Response({'text': result['text'], 'tokens': result['total_tokens']})
    except Exception as e:
        _log_error('api_docs', request, str(e), inputs)
        return Response({'error': str(e)}, status=500)


# ── MEETING NOTES SUMMARIZER ───────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
def meeting_notes_summarizer(request):
    notes = request.data.get('notes', '').strip()
    style = request.data.get('style', 'action-items')

    if not notes:
        return Response({'error': 'notes is required'}, status=400)

    inputs = {'notes': notes[:5000], 'style': style}
    try:
        result = generate_meeting_notes(notes, style)
        _log('meeting_notes', request, result, inputs)
        return Response({'text': result['text'], 'tokens': result['total_tokens']})
    except Exception as e:
        _log_error('meeting_notes', request, str(e), inputs)
        return Response({'error': str(e)}, status=500)
