"""
Real-time error alerting — so you find out about errors WITHOUT having
to manually tail log files or SSH into the server.

Two layers:
  1. Django's built-in ADMINS email — fires automatically on any
     unhandled 500 error, using your EXISTING email settings (you
     already have EMAIL_HOST/EMAIL_HOST_USER configured).
  2. Custom log handler that posts to Slack on WARNING+ from your
     own apps (Stripe webhook failures, AI tool errors, etc) — these
     are caught exceptions that DON'T produce a Django 500, so the
     ADMINS email alone won't catch them. This is the gap that matters
     most for you, since your webhook handlers all do:
         except Exception as e:
             logger.error(f'...: {e}')
     which silently swallows the error unless something is watching
     the error log in real time.
"""

# ── STEP 1 — Add to config/settings/base.py ────────────────────────────
"""
ADMINS = [('Rohit', config('ADMIN_EMAIL', default='you@arhat.info'))]
SERVER_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@arhat.info')

# Add 'mail_admins' handler + wire into LOGGING (see logging_update.py):
LOGGING['handlers']['mail_admins'] = {
    'level':     'ERROR',
    'class':     'django.utils.log.AdminEmailHandler',
    'formatter': 'verbose',
}
LOGGING['loggers']['django']['handlers'].append('mail_admins')
"""

# ── STEP 2 — Slack webhook handler for your own app loggers ────────────
# Save this as apps/core/log_handlers.py

import logging
import json
import requests
from django.conf import settings


class SlackErrorHandler(logging.Handler):
    """
    Custom logging handler — posts WARNING/ERROR/CRITICAL records to a
    Slack channel via Incoming Webhook. Add to the 'apps' logger so any
    logger.error(...) call anywhere in apps/ triggers an instant Slack
    message instead of silently writing to a file nobody is watching.
    """

    def emit(self, record):
        webhook_url = getattr(settings, 'SLACK_ERROR_WEBHOOK_URL', '')
        if not webhook_url:
            return  # not configured — fail silently, don't break the app

        try:
            message = self.format(record)
            emoji = {
                'WARNING':  ':warning:',
                'ERROR':    ':rotating_light:',
                'CRITICAL': ':fire:',
            }.get(record.levelname, ':speech_balloon:')

            payload = {
                'text': f'{emoji} *{record.levelname}* in `{record.name}`\n```{message[:1500]}```'
            }
            requests.post(webhook_url, json=payload, timeout=3)
        except Exception:
            pass  # never let logging itself crash the request


# ── STEP 3 — Wire SlackErrorHandler into LOGGING ────────────────────────
"""
Add to LOGGING['handlers'] in base.py:

LOGGING['handlers']['slack'] = {
    'level':     'WARNING',
    'class':     'apps.core.log_handlers.SlackErrorHandler',
    'formatter': 'simple',
}

Then add 'slack' to the handlers list for the 'apps' logger:

LOGGING['loggers']['apps']['handlers'] = ['console', 'file_all', 'file_errors', 'slack']
"""

# ── STEP 4 — .env ────────────────────────────────────────────────────
"""
ADMIN_EMAIL=you@arhat.info
SLACK_ERROR_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
"""

# ── How to get a Slack webhook URL (free, 5 minutes) ───────────────────
"""
1. Go to https://api.slack.com/apps -> Create New App -> From scratch
2. Name it "Arhat Error Bot", pick your workspace
3. Left sidebar -> Incoming Webhooks -> toggle ON
4. Click "Add New Webhook to Workspace" -> choose a channel (e.g. #errors)
5. Copy the webhook URL -> paste into .env as SLACK_ERROR_WEBHOOK_URL
"""
