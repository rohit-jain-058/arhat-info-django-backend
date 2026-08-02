"""
AI tool views — updated to:
  1. Require IsAIToolsSubscriber (ai_tools or full tier only)
  2. Enforce per-plan daily quota via ai_tool_endpoint decorator
  3. Log every request tied to the user (not just IP) via AIToolRequest.user

Replaces apps/tools/views/ai_views.py.
"""
from rest_framework.decorators import api_view, permission_classes

from apps.subscriptions.permissions import IsAIToolsSubscriber
from ..ai_usage import ai_tool_endpoint
from ..gpt_service import (
    generate_prompt, generate_email, generate_linkedin_post,
    generate_cover_letter, generate_resume_summary, generate_sql,
    generate_regex, generate_api_docs, generate_meeting_notes,
)
from ..gpt_service import (
    generate_upwork_proposal,
    generate_recruiter_reply,
    match_job_description,
    generate_cron,
    analyze_api_request,
)
import logging
logger = logging.getLogger(__name__)





# ── 1. UPWORK PROPOSAL GENERATOR ──────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('upwork_proposal')
def upwork_proposal_generator(request):
    job_description = request.data.get('job_description', '').strip()
    skills          = request.data.get('skills', '').strip()
    experience      = request.data.get('experience', '').strip()
    rate            = request.data.get('rate', '')
    tone            = request.data.get('tone', 'professional')

    if not job_description:
        raise ValueError('job_description is required')
    if not skills:
        raise ValueError('skills is required')

    inputs = {
        'job_description': job_description[:3000],
        'skills':          skills,
        'experience':      experience,
        'rate':            rate,
        'tone':            tone,
    }
    result = generate_upwork_proposal(job_description, skills, experience, rate, tone)
    return result, inputs


# ── 2. LINKEDIN RECRUITER REPLY ────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('recruiter_reply')
def recruiter_reply_generator(request):
    recruiter_message = request.data.get('recruiter_message', '').strip()
    situation         = request.data.get('situation', 'ask_more')
    user_name         = request.data.get('name', '')
    tone              = request.data.get('tone', 'professional')

    if not recruiter_message:
        raise ValueError('recruiter_message is required')

    valid_situations = ['interested', 'not_interested', 'maybe', 'ask_more']
    if situation not in valid_situations:
        situation = 'ask_more'

    inputs = {
        'recruiter_message': recruiter_message[:2000],
        'situation':         situation,
        'name':              user_name,
        'tone':              tone,
    }
    result = generate_recruiter_reply(recruiter_message, situation, user_name, tone)
    return result, inputs


# ── 3. JOB DESCRIPTION MATCHER ────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('job_matcher')
def job_description_matcher(request):
    job_description    = request.data.get('job_description', '').strip()
    resume_or_skills   = request.data.get('resume_or_skills', '').strip()
    output_format      = request.data.get('output_format', 'analysis')

    if not job_description:
        raise ValueError('job_description is required')
    if not resume_or_skills:
        raise ValueError('resume_or_skills is required')

    valid_formats = ['analysis', 'cover_letter', 'keywords', 'gap_analysis']
    if output_format not in valid_formats:
        output_format = 'analysis'

    inputs = {
        'job_description':  job_description[:3000],
        'resume_or_skills': resume_or_skills[:3000],
        'output_format':    output_format,
    }
    result = match_job_description(job_description, resume_or_skills, output_format)
    return result, inputs


# ── 4. CRON GENERATOR ─────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('cron_gen')
def cron_generator(request):
    description = request.data.get('description', '').strip()
    timezone    = request.data.get('timezone', 'UTC')
    format_type = request.data.get('format', 'standard')

    if not description:
        raise ValueError('description is required')

    valid_formats = ['standard', 'quartz', 'aws']
    if format_type not in valid_formats:
        format_type = 'standard'

    inputs = {
        'description': description,
        'timezone':    timezone,
        'format':      format_type,
    }
    result = generate_cron(description, timezone, format_type)
    return result, inputs


# ── 5. API TESTER ─────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('api_tester')
def api_tester(request):
    method          = request.data.get('method', 'GET').upper()
    url             = request.data.get('url', '').strip()
    headers         = request.data.get('headers', '')
    body            = request.data.get('body', '')
    response_status = request.data.get('response_status', '')
    response_body   = request.data.get('response_body', '')
    question        = request.data.get('question', '')

    if not url:
        raise ValueError('url is required')

    valid_methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
    if method not in valid_methods:
        method = 'GET'

    inputs = {
        'method':          method,
        'url':             url,
        'headers':         headers[:2000],
        'body':            body[:3000],
        'response_status': response_status,
        'response_body':   response_body[:3000],
        'question':        question,
    }
    result = analyze_api_request(
        method, url, headers, body,
        response_status, response_body, question
    )
    return result, inputs


# ── PROMPT GENERATOR ───────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('prompt_gen')
def prompt_generator(request):
    goal    = request.data.get('goal', '').strip()
    context = request.data.get('context', '')
    fmt     = request.data.get('format', 'detailed')
    if not goal:
        raise ValueError('goal is required')
    inputs = {'goal': goal, 'context': context, 'format': fmt}
    result = generate_prompt(goal, context, fmt)
    return result, inputs


# ── EMAIL GENERATOR ────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('email_gen')
def email_generator(request):
    purpose   = request.data.get('purpose', 'follow-up')
    recipient = request.data.get('recipient', '')
    context   = request.data.get('context', '').strip()
    tone      = request.data.get('tone', 'professional')
    inputs = {'purpose': purpose, 'recipient': recipient, 'context': context, 'tone': tone}
    result = generate_email(purpose, recipient, context, tone)
    return result, inputs


# ── LINKEDIN POST GENERATOR ────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('linkedin_post')
def linkedin_generator(request):
    topic = request.data.get('topic', '').strip()
    hook  = request.data.get('hook', '')
    style = request.data.get('style', 'thought-leadership')
    if not topic:
        raise ValueError('topic is required')
    inputs = {'topic': topic, 'hook': hook, 'style': style}
    result = generate_linkedin_post(topic, hook, style)
    return result, inputs


# ── COVER LETTER GENERATOR ─────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('cover_letter')
def cover_letter_generator(request):
    role        = request.data.get('role', '').strip()
    company     = request.data.get('company', '')
    skills      = request.data.get('skills', '')
    achievement = request.data.get('achievement', '')
    if not role:
        raise ValueError('role is required')
    inputs = {'role': role, 'company': company, 'skills': skills, 'achievement': achievement}
    result = generate_cover_letter(role, company, skills, achievement)
    return result, inputs


# ── RESUME SUMMARY GENERATOR ───────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('resume_summary')
def resume_summary_generator(request):
    role   = request.data.get('role', '').strip()
    years  = request.data.get('years', '')
    skills = request.data.get('skills', '')
    goal   = request.data.get('goal', '')
    if not role:
        raise ValueError('role is required')
    inputs = {'role': role, 'years': years, 'skills': skills, 'goal': goal}
    result = generate_resume_summary(role, years, skills, goal)
    return result, inputs


# ── SQL GENERATOR ──────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('sql_gen')
def sql_generator(request):
    question = request.data.get('question', '').strip()
    schema   = request.data.get('schema', '')
    dialect  = request.data.get('dialect', 'PostgreSQL')
    if not question:
        raise ValueError('question is required')
    inputs = {'question': question, 'schema': schema, 'dialect': dialect}
    result = generate_sql(question, schema, dialect)
    return result, inputs


# ── REGEX GENERATOR ────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('regex_gen')
def regex_generator(request):
    description = request.data.get('description', '').strip()
    example     = request.data.get('example', '')
    language    = request.data.get('language', 'JavaScript')
    if not description:
        raise ValueError('description is required')
    inputs = {'description': description, 'example': example, 'language': language}
    result = generate_regex(description, example, language)
    return result, inputs


# ── API DOCS GENERATOR ─────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('api_docs')
def api_docs_generator(request):
    endpoint = request.data.get('endpoint', '').strip()
    fmt      = request.data.get('format', 'Markdown')
    if not endpoint:
        raise ValueError('endpoint is required')
    inputs = {'endpoint': endpoint[:2000], 'format': fmt}
    result = generate_api_docs(endpoint, fmt)
    return result, inputs


# ── MEETING NOTES SUMMARIZER ───────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('meeting_notes')
def meeting_notes_summarizer(request):
    notes = request.data.get('notes', '').strip()
    style = request.data.get('style', 'action-items')
    if not notes:
        raise ValueError('notes is required')
    inputs = {'notes': notes[:5000], 'style': style}
    result = generate_meeting_notes(notes, style)
    return result, inputs
