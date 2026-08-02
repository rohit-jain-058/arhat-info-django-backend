"""
All tool URLs.

Mount in config/urls.py:
  path('api/tools/', include('apps.tools.urls')),
"""
from django.urls import path
from .views import network_views as nv
from .views import ai_views      as av
from .views import file_views    as fv
from . import history_views as hv
from . import views as v
urlpatterns = [

    # ── Network Tools ──────────────────────────────────────────────
    path('myip/',              nv.myip,              name='tool_myip'),
    path('iplookup/',          nv.iplookup,          name='tool_iplookup'),
    path('hostname/',          nv.hostname,          name='tool_hostname'),
    path('whois/',             nv.whois,             name='tool_whois'),
    path('blacklist/',         nv.blacklist,         name='tool_blacklist'),
    path('portscan/',          nv.portscan,          name='tool_portscan'),
    path('traceroute/',        nv.traceroute,        name='tool_traceroute'),
    path('dns/',               nv.dns_lookup,        name='tool_dns'),
    path('useragent/',         nv.useragent,         name='tool_useragent'),
    path('speedtest/',         nv.speedtest,         name='tool_speedtest'),
    path('speedtest/upload/',  nv.speedtest_upload,  name='tool_speedtest_upload'),
    path('ping/',              nv.ping,              name='tool_ping'),

    # ── AI Tools ───────────────────────────────────────────────────
    path('ai/prompt/',         av.prompt_generator,          name='ai_prompt'),
    path('ai/email/',          av.email_generator,           name='ai_email'),
    path('ai/linkedin/',       av.linkedin_generator,        name='ai_linkedin'),
    path('ai/cover-letter/',   av.cover_letter_generator,    name='ai_cover_letter'),
    path('ai/resume-summary/', av.resume_summary_generator,  name='ai_resume_summary'),
    path('ai/sql/',            av.sql_generator,             name='ai_sql'),
    path('ai/regex/',          av.regex_generator,           name='ai_regex'),
    path('ai/api-docs/',       av.api_docs_generator,        name='ai_api_docs'),
    path('ai/meeting-notes/',  av.meeting_notes_summarizer,  name='ai_meeting_notes'),
    path('ai/history/',        hv.ai_history, name='ai_history'),
    path('ai/upwork-proposal/',  av.upwork_proposal_generator,  name='ai_upwork_proposal'),
path('ai/recruiter-reply/',  av.recruiter_reply_generator,   name='ai_recruiter_reply'),
path('ai/job-matcher/',      av.job_description_matcher,     name='ai_job_matcher'),
path('ai/cron/',             av.cron_generator,              name='ai_cron'),
path('ai/api-tester/',       av.api_tester,                  name='ai_api_tester'),

    # ── File Tools ─────────────────────────────────────────────────
    path('pdf/merge/',         fv.pdf_merge,         name='tool_pdf_merge'),
    path('pdf/minify/',        fv.pdf_minify,        name='tool_pdf_minify'),
]
