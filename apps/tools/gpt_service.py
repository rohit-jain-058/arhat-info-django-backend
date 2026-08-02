"""
GPT service — all AI tool generation via OpenAI GPT-4o.
Used by the AI tools Django views.
"""
import logging
import time
from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def gpt_generate(system: str, user: str, model: str = 'gpt-4o', max_tokens: int = 1000) -> dict:
    """
    Call GPT and return result with token usage.
    Returns: { 'text': str, 'prompt_tokens': int, 'completion_tokens': int, 'total_tokens': int }
    """
    start = time.time()
    try:
        response = get_client().chat.completions.create(
            model       = model,
            max_tokens  = max_tokens,
            temperature = 0.7,
            messages    = [
                {'role': 'system', 'content': system},
                {'role': 'user',   'content': user},
            ],
        )
        text  = response.choices[0].message.content or ''
        usage = response.usage
        ms    = int((time.time() - start) * 1000)
        logger.info(f'[GPT] {model} | {usage.total_tokens} tokens | {ms}ms')
        return {
            'text':              text,
            'prompt_tokens':     usage.prompt_tokens,
            'completion_tokens': usage.completion_tokens,
            'total_tokens':      usage.total_tokens,
            'model':             model,
            'duration_ms':       ms,
        }
    except Exception as e:
        logger.error(f'[GPT] Error: {e}')
        raise


# ── TOOL-SPECIFIC PROMPTS & CALLERS ───────────────────────────────────

def generate_prompt(goal: str, context: str = '', fmt: str = 'detailed') -> dict:
    system = "You are an expert at writing highly effective AI prompts. Write only the prompt itself — no explanation, no preamble."
    user   = f"Create a {fmt} AI prompt for:\nGoal: {goal}\nContext: {context or 'none'}\n\nWrite only the prompt."
    return gpt_generate(system, user, max_tokens=600)


def generate_email(purpose: str, recipient: str, context: str, tone: str) -> dict:
    system = "You are an expert business writer. Write concise, effective emails."
    user   = f"Write a {tone} {purpose} email.\nTo: {recipient or 'client'}\nContext: {context}\n\nInclude a subject line on the first line prefixed with 'Subject: '"
    return gpt_generate(system, user, max_tokens=600)


def generate_linkedin_post(topic: str, hook: str, style: str) -> dict:
    system = "You are a LinkedIn content expert. Write authentic, engaging posts that get traction."
    user   = f"Write a {style} LinkedIn post about: {topic}\nAngle: {hook or 'insightful and engaging'}\n\n150-300 words. Include 3-5 relevant hashtags at the end."
    return gpt_generate(system, user, max_tokens=500)


def generate_cover_letter(role: str, company: str, skills: str, achievement: str) -> dict:
    system = "You are an expert career coach and professional writer."
    user   = f"""Write a compelling cover letter for:
Role: {role}
Company: {company or 'the company'}
Key skills: {skills}
Top achievement: {achievement}

3 paragraphs. Specific, not generic. Address as 'Dear Hiring Manager'."""
    return gpt_generate(system, user, max_tokens=600)


def generate_resume_summary(role: str, years: str, skills: str, goal: str) -> dict:
    system = "You are an expert resume writer. Write concise, ATS-friendly professional summaries."
    user   = f"""Resume summary for:
Role: {role}
Experience: {years or '?'} years
Skills: {skills}
Goal: {goal or 'advance in the field'}

3-4 sentences. Specific and quantified where possible. No filler words."""
    return gpt_generate(system, user, max_tokens=300)


def generate_sql(question: str, schema: str = '', dialect: str = 'PostgreSQL') -> dict:
    system = f"You are a senior {dialect} database engineer. Write clean, optimized SQL."
    user   = f"""{dialect} SQL query for:
{question}

{f'Schema:{chr(10)}{schema}' if schema else ''}

Write only the SQL with brief comments for complex parts."""
    return gpt_generate(system, user, max_tokens=800)


def generate_regex(description: str, example: str = '', language: str = 'JavaScript') -> dict:
    system = f"You are a regex expert. Generate precise, well-explained regex patterns for {language}."
    user   = f"""Generate a regex for {language} that:
{description}

Example input: {example or 'none provided'}

Provide:
1. The regex pattern
2. Brief explanation of each part
3. Code example in {language}"""
    return gpt_generate(system, user, max_tokens=600)


def generate_api_docs(endpoint: str, fmt: str = 'Markdown') -> dict:
    system = "You are a senior API documentation writer. Write clear, complete API documentation."
    user   = f"""Write complete API documentation in {fmt} format for:

{endpoint}

Include: description, HTTP method, URL, parameters, request body, response format, example request, example response, error codes."""
    return gpt_generate(system, user, max_tokens=1000)


def generate_meeting_notes(notes: str, style: str = 'action-items') -> dict:
    system = "You are an expert meeting facilitator and business writer."
    style_instructions = {
        'action-items':      'Extract all decisions and action items with owners and deadlines.',
        'executive-summary': 'Write a 3-5 sentence executive summary.',
        'meeting-minutes':   'Write full structured meeting minutes with attendees, agenda, decisions, and next steps.',
    }
    user = f"""Summarize these meeting notes:

{notes}

Format: {style_instructions.get(style, style_instructions['action-items'])}"""
    return gpt_generate(system, user, max_tokens=800)


# ── NEW TOOLS (added in second batch) ─────────────────────────────────

def generate_upwork_proposal(
    job_description: str,
    skills: str,
    experience: str,
    rate: str = '',
    tone: str = 'professional',
) -> dict:
    system = """You are an expert Upwork freelancer who writes winning proposals.
Write proposals that are concise, specific, and client-focused.
Never use generic openers like "I am writing to express my interest".
Start with the client's problem, then show you understand it, then offer your solution.
Include a specific question at the end to show genuine interest."""

    user = f"""Write a winning Upwork proposal for this job:

Job Description:
{job_description}

My Skills: {skills}
My Experience: {experience}
{f'My Rate: {rate}' if rate else ''}
Tone: {tone}

Write a proposal (150-250 words) that:
1. Opens with the client's specific problem (no generic intros)
2. Shows understanding of their needs
3. Briefly describes how I'd solve it
4. Mentions 1-2 relevant past results/examples
5. Ends with a specific question about their project
{f'6. Naturally mentions my rate of {rate}' if rate else ''}"""

    return gpt_generate(system, user, max_tokens=600)


def generate_recruiter_reply(
    recruiter_message: str,
    situation: str,
    user_name: str = '',
    tone: str = 'professional',
) -> dict:
    situation_instructions = {
        'interested':     'Express genuine interest. Ask about next steps, timeline, and compensation range.',
        'not_interested': 'Decline politely and professionally. Keep the relationship warm for future opportunities. Do not over-explain.',
        'maybe':          'Show cautious interest. Ask clarifying questions about the role, company culture, and compensation before committing.',
        'ask_more':       'Express interest but ask specific questions about the role, tech stack, team size, remote policy, and compensation before deciding.',
    }

    system = "You are an expert at professional communication on LinkedIn. Write replies that are genuine, not corporate-sounding, and appropriately concise."

    user = f"""Write a LinkedIn reply to this recruiter message:

Recruiter Message:
{recruiter_message}

My situation: {situation_instructions.get(situation, situation_instructions['ask_more'])}
{f'My name: {user_name}' if user_name else ''}
Tone: {tone}

Write a reply (50-150 words) that sounds human and genuine, not templated.
Do not start with "Thank you for reaching out" or similar clichés."""

    return gpt_generate(system, user, max_tokens=400)


def match_job_description(
    job_description: str,
    resume_or_skills: str,
    output_format: str = 'analysis',
) -> dict:
    format_instructions = {
        'analysis': """Provide:
1. Match Score (0-100%) with brief reasoning
2. Top 5 matching strengths from my profile
3. Top 3 gaps or missing requirements
4. 3 keywords from the JD I should emphasize in my application
5. One-line recommendation (apply / apply with modifications / skip)""",

        'cover_letter': """Write a targeted cover letter (200-300 words) that:
- Opens with a specific accomplishment matching their top requirement
- Addresses their exact pain points from the job description
- Uses keywords from the job description naturally
- Ends with a confident, specific call to action""",

        'keywords': """Extract and categorize:
1. Must-have technical skills mentioned
2. Nice-to-have skills mentioned
3. Soft skills/culture keywords
4. Industry-specific terminology
5. Which of these appear in my profile (matched) vs missing (gaps)
Format as a clear table.""",

        'gap_analysis': """Provide a detailed gap analysis:
1. Requirements I clearly meet (with evidence from my profile)
2. Requirements I partially meet (explain what's missing)
3. Requirements I don't meet at all
4. Suggested ways to address the top 2 gaps before applying
5. Overall recommendation""",
    }

    system = "You are an expert career coach and ATS specialist who helps candidates optimize their job applications."

    user = f"""Analyze this job match:

Job Description:
{job_description}

My Profile/Skills/Resume:
{resume_or_skills}

{format_instructions.get(output_format, format_instructions['analysis'])}"""

    return gpt_generate(system, user, max_tokens=800)


def generate_cron(
    description: str,
    timezone: str = 'UTC',
    format_type: str = 'standard',
) -> dict:
    format_instructions = {
        'standard': '5-field standard cron (minute hour day-of-month month day-of-week)',
        'quartz':   '6-field Quartz cron (seconds minute hour day-of-month month day-of-week)',
        'aws':      'AWS EventBridge/CloudWatch cron format (6-field with year)',
    }

    system = """You are a cron expression expert. Generate accurate cron expressions and explain them clearly.
Always validate your expression is correct before providing it.
For ambiguous schedules, ask for clarification or provide multiple options."""

    user = f"""Generate a cron expression for:
"{description}"

Timezone: {timezone}
Format: {format_instructions.get(format_type, format_instructions['standard'])}

Provide:
1. The exact cron expression (formatted as code)
2. Plain English confirmation of what it does (verify it matches the request)
3. Next 5 execution times (relative, e.g. "next Monday at 9:00 AM UTC")
4. Any edge cases or gotchas to be aware of (e.g. "doesn't account for DST")
5. Alternative expressions if there are multiple valid approaches"""

    return gpt_generate(system, user, max_tokens=600)


def analyze_api_request(
    method: str,
    url: str,
    headers: str = '',
    body: str = '',
    response_status: str = '',
    response_body: str = '',
    question: str = '',
) -> dict:
    system = """You are a senior API engineer and HTTP expert.
Analyze API requests and responses, identify issues, and provide clear actionable guidance.
When analyzing errors, always explain the root cause and provide a concrete fix."""

    has_response = bool(response_status or response_body)
    has_question = bool(question)

    parts = [f"Method: {method}", f"URL: {url}"]
    if headers: parts.append(f"Headers:\n{headers}")
    if body:    parts.append(f"Request Body:\n{body}")

    analysis_request = []
    if has_response:
        if response_status: parts.append(f"Response Status: {response_status}")
        if response_body:   parts.append(f"Response Body:\n{response_body[:2000]}")
        analysis_request.append("""Analyze this API response:
        1. Status code meaning and whether this is expected
        2. If error: root cause and exact fix
        3. Response structure breakdown (key fields and their purpose)
        4. Any security concerns (exposed tokens, sensitive data, etc.)
        5. Performance notes (if relevant from the response)""")

    if has_question:
        analysis_request.append(f"Answer this specific question: {question}")

    if not has_response and not has_question:
        analysis_request.append("""Review this API request and provide:
1. Potential issues with the request structure
2. Missing headers that are typically required
3. Security best practices to apply
4. Suggested improvements""")

    user = '\n'.join(parts) + '\n\n' + '\n\n'.join(analysis_request)

    return gpt_generate(system, user, max_tokens=800)
def generate_upwork_proposal(
    job_description: str,
    skills: str,
    experience: str,
    rate: str = '',
    tone: str = 'professional',
) -> dict:
    system = """You are an expert Upwork freelancer who writes winning proposals.
Write proposals that are concise, specific, and client-focused.
Never use generic openers like "I am writing to express my interest".
Start with the client's problem, then show you understand it, then offer your solution.
Include a specific question at the end to show genuine interest."""

    user = f"""Write a winning Upwork proposal for this job:

Job Description:
{job_description}

My Skills: {skills}
My Experience: {experience}
{f'My Rate: {rate}' if rate else ''}
Tone: {tone}

Write a proposal (150-250 words) that:
1. Opens with the client's specific problem (no generic intros)
2. Shows understanding of their needs
3. Briefly describes how I'd solve it
4. Mentions 1-2 relevant past results/examples
5. Ends with a specific question about their project
{f'6. Naturally mentions my rate of {rate}' if rate else ''}"""

    return gpt_generate(system, user, max_tokens=600)


# ── 2. LINKEDIN RECRUITER REPLY ────────────────────────────────────────
def generate_recruiter_reply(
    recruiter_message: str,
    situation: str,
    user_name: str = '',
    tone: str = 'professional',
) -> dict:
    """
    situation: 'interested' | 'not_interested' | 'maybe' | 'ask_more'
    """
    situation_instructions = {
        'interested': 'Express genuine interest. Ask about next steps, timeline, and compensation range.',
        'not_interested': 'Decline politely and professionally. Keep the relationship warm for future opportunities. Do not over-explain.',
        'maybe': 'Show cautious interest. Ask clarifying questions about the role, company culture, and compensation before committing.',
        'ask_more': 'Express interest but ask specific questions about the role, tech stack, team size, remote policy, and compensation before deciding.',
    }

    system = "You are an expert at professional communication on LinkedIn. Write replies that are genuine, not corporate-sounding, and appropriately concise."

    user = f"""Write a LinkedIn reply to this recruiter message:

Recruiter Message:
{recruiter_message}

My situation: {situation_instructions.get(situation, situation_instructions['ask_more'])}
{f'My name: {user_name}' if user_name else ''}
Tone: {tone}

Write a reply (50-150 words) that sounds human and genuine, not templated.
Do not start with "Thank you for reaching out" or similar clichés."""

    return gpt_generate(system, user, max_tokens=400)


# ── 3. JOB DESCRIPTION MATCHER ────────────────────────────────────────
def match_job_description(
    job_description: str,
    resume_or_skills: str,
    output_format: str = 'analysis',
) -> dict:
    """
    output_format: 'analysis' | 'cover_letter' | 'keywords' | 'gap_analysis'
    """
    format_instructions = {
        'analysis': """Provide:
1. Match Score (0-100%) with brief reasoning
2. Top 5 matching strengths from my profile
3. Top 3 gaps or missing requirements
4. 3 keywords from the JD I should emphasize in my application
5. One-line recommendation (apply / apply with modifications / skip)""",

        'cover_letter': """Write a targeted cover letter (200-300 words) that:
- Opens with a specific accomplishment matching their top requirement
- Addresses their exact pain points from the job description
- Uses keywords from the job description naturally
- Ends with a confident, specific call to action""",

        'keywords': """Extract and categorize:
1. Must-have technical skills mentioned
2. Nice-to-have skills mentioned
3. Soft skills/culture keywords
4. Industry-specific terminology
5. Which of these appear in my profile (matched) vs missing (gaps)
Format as a clear table.""",

        'gap_analysis': """Provide a detailed gap analysis:
1. Requirements I clearly meet (with evidence from my profile)
2. Requirements I partially meet (explain what's missing)
3. Requirements I don't meet at all
4. Suggested ways to address the top 2 gaps before applying
5. Overall recommendation""",
    }

    system = "You are an expert career coach and ATS specialist who helps candidates optimize their job applications."

    user = f"""Analyze this job match:

Job Description:
{job_description}

My Profile/Skills/Resume:
{resume_or_skills}

{format_instructions.get(output_format, format_instructions['analysis'])}"""

    return gpt_generate(system, user, max_tokens=800)


# ── 4. CRON GENERATOR ─────────────────────────────────────────────────
def generate_cron(
    description: str,
    timezone: str = 'UTC',
    format_type: str = 'standard',
) -> dict:
    """
    format_type: 'standard' (5-field) | 'quartz' (6-field with seconds) | 'aws' (EventBridge)
    """
    format_instructions = {
        'standard': '5-field standard cron (minute hour day-of-month month day-of-week)',
        'quartz':   '6-field Quartz cron (seconds minute hour day-of-month month day-of-week)',
        'aws':      'AWS EventBridge/CloudWatch cron format (6-field with year)',
    }

    system = """You are a cron expression expert. Generate accurate cron expressions and explain them clearly.
Always validate your expression is correct before providing it.
For ambiguous schedules, ask for clarification or provide multiple options."""

    user = f"""Generate a cron expression for:
"{description}"

Timezone: {timezone}
Format: {format_instructions.get(format_type, format_instructions['standard'])}

Provide:
1. The exact cron expression (formatted as code)
2. Plain English confirmation of what it does (verify it matches the request)
3. Next 5 execution times (relative, e.g. "next Monday at 9:00 AM UTC")
4. Any edge cases or gotchas to be aware of (e.g. "doesn't account for DST")
5. Alternative expressions if there are multiple valid approaches"""

    return gpt_generate(system, user, max_tokens=600)


# ── 5. API TESTER ─────────────────────────────────────────────────────
def analyze_api_request(
    method: str,
    url: str,
    headers: str = '',
    body: str = '',
    response_status: str = '',
    response_body: str = '',
    question: str = '',
) -> dict:
    """
    Two modes:
    - If response_status/response_body provided: analyze the response
    - If question provided: help build/debug the request
    - If both: full analysis
    """
    system = """You are a senior API engineer and HTTP expert.
Analyze API requests and responses, identify issues, and provide clear actionable guidance.
When analyzing errors, always explain the root cause and provide a concrete fix."""

    has_response = bool(response_status or response_body)
    has_question = bool(question)

    parts = [f"Method: {method}", f"URL: {url}"]
    if headers: parts.append(f"Headers:\n{headers}")
    if body:    parts.append(f"Request Body:\n{body}")

    analysis_request = []
    if has_response:
        if response_status: parts.append(f"Response Status: {response_status}")
        if response_body:   parts.append(f"Response Body:\n{response_body[:2000]}")
        analysis_request.append("""Analyze this API response:
1. Status code meaning and whether this is expected
2. If error: root cause and exact fix
3. Response structure breakdown (key fields and their purpose)
4. Any security concerns (exposed tokens, sensitive data, etc.)
5. Performance notes (if relevant from the response)""")

    if has_question:
        analysis_request.append(f"Answer this specific question: {question}")

    if not has_response and not has_question:
        analysis_request.append("""Review this API request and provide:
1. Potential issues with the request structure
2. Missing headers that are typically required
3. Security best practices to apply
4. Suggested improvements""")

    user = '\n'.join(parts) + '\n\n' + '\n\n'.join(analysis_request)

    return gpt_generate(system, user, max_tokens=800)
