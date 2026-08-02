"""
Staging settings — mirrors production but with relaxed security for QA.
"""
from .base import *  # noqa
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from decouple import config

DEBUG = False


# ── Security ──────────────────────────────────────────────────────────
SESSION_COOKIE_SECURE   = True
CSRF_COOKIE_SECURE      = True
SECURE_SSL_REDIRECT     = True
SECURE_HSTS_SECONDS     = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# ── Static/Media via S3 ───────────────────────────────────────────────

from .base import *
import os

DEBUG = False

# Lambda sets AWS_LAMBDA_FUNCTION_NAME in the environment
IS_LAMBDA = bool(os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))

# Allowed hosts — add your API Gateway URL and custom domain
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '.execute-api.us-east-1.amazonaws.com',   # API Gateway URL
    'api.arhatinfo.com',                        # your custom domain
    '*.arhat.info',
    '*.run.app',
    'dev.arhat.info',
    'lrk6jg5p7z25wg3cq5d47cfhe40xyraw.lambda-url.us-east-1.on.aws',
    '75hmr4ydr5.execute-api.us-east-1.amazonaws.com',
    'chatbot-arhatinfo-xzkib7kizq-uk.a.run.app',
    config('ALLOWED_HOSTS', default=''),
]

# Database — use RDS PostgreSQL on production
# Lambda cannot connect to localhost
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     config('DB_NAME'),
        'USER':     config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST':     config('DB_HOST'),        # RDS endpoint
        'PORT':     config('DB_PORT', default='5432'),
    }
}



# CORS — allow your Firebase frontend
CORS_ALLOWED_ORIGINS = [
    'https://arhat.info',
    'https://www.arhat.info',
    'https://arhatinfo.web.app',
    'https://arhatinfo.firebaseapp.com',
    'http://localhost:3000',
    'https://*.arhat.info',
    'https://*.run.app',
    'https://arhatinfo.com'
]
CORS_ALLOW_CREDENTIALS = True

# Security
SECURE_SSL_REDIRECT            = False   # API Gateway handles SSL
SESSION_COOKIE_SECURE          = True
CSRF_COOKIE_SECURE             = True
SECURE_HSTS_SECONDS            = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
