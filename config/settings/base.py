from pathlib import Path
from datetime import timedelta
import dj_database_url
from decouple import config
import os
import json
import sys
import logging



BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = BASE_DIR / 'logs'
os.makedirs(LOG_DIR, exist_ok=True)

SECRET_KEY   = config('SECRET_KEY')
DEBUG        = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS= config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')
OPENAI_API_KEY = config('OPENAI_API_KEY')
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY')
EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = config('EMAIL_HOST',          default='smtp.gmail.com')
EMAIL_PORT          = config('EMAIL_PORT',           default=587, cast=int)
EMAIL_USE_TLS       = config('EMAIL_USE_TLS',        default=True, cast=bool)
EMAIL_HOST_USER     = config('EMAIL_HOST_USER',      default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD',  default='')
DEFAULT_FROM_EMAIL  = config('DEFAULT_FROM_EMAIL',   default='contact@arhat.info')
TEAM_EMAIL          = config('TEAM_EMAIL',           default='contact@arhat.info')
STRIPE_SECRET_KEY      = config('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = config('STRIPE_PUBLISHABLE_KEY')
STRIPE_WEBHOOK_SECRET  = config('STRIPE_WEBHOOK_SECRET', default='')
FRONTEND_URL           = config('FRONTEND_URL', default='https://arhat.info')
GOOGLE_CLIENT_ID    = config('GOOGLE_CLIENT_ID', default='')
DATA_UPLOAD_MAX_MEMORY_SIZE = 24 * 1024 * 1024  # 10 MB


# ── Apps ──────────────────────────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'django_celery_beat',
    'django_celery_results',
    'storages',
]

LOCAL_APPS = [
    'apps.resumes',
    'apps.core',
    'apps.tools', 
    'apps.authentication',
    'apps.chatbot',
    'apps.subscriptions',
    
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

SITE_ID = 1

# ── Middleware ────────────────────────────────────────────────────────
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.subscriptions.middleware.SubscriptionMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF    = 'config.urls'
WSGI_APPLICATION= 'config.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ── Database ──────────────────────────────────────────────────────────
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

# ── Auth ──────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'authentication.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── DRF ───────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'apps.core.pagination.StandardResultsSetPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_RENDERER_CLASSES': ('rest_framework.renderers.JSONRenderer',),
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
}

# ── JWT ───────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':    timedelta(minutes=config('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', default=60, cast=int)),
    'REFRESH_TOKEN_LIFETIME':   timedelta(days=config('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=7, cast=int)),
    'ROTATE_REFRESH_TOKENS':    True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN':        True,
    'ALGORITHM':                'HS256',
    'AUTH_HEADER_TYPES':        ('Bearer',),
    'USER_ID_FIELD':            'id',
    'USER_ID_CLAIM':            'user_id',
    'TOKEN_OBTAIN_SERIALIZER':  'apps.authentication.serializers.CustomTokenObtainPairSerializer',
}

# ── CORS ──────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS  = config('CORS_ALLOWED_ORIGINS', default='').split(',')
CORS_ALLOW_CREDENTIALS= True

# ── Celery ────────────────────────────────────────────────────────────
CELERY_RESULT_BACKEND     = config('CELERY_RESULT_BACKEND',default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT     = ['json']
CELERY_TASK_SERIALIZER    = 'json'
CELERY_RESULT_SERIALIZER  = 'json'
CELERY_TIMEZONE           = 'UTC'
CELERY_BEAT_SCHEDULER     = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT    = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT=25 * 60

# ── Email ─────────────────────────────────────────────────────────────
EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT          = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS       = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER     = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL  = config('DEFAULT_FROM_EMAIL', default='noreply@example.com')

# ── i18n ──────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'UTC'
USE_I18N      = True
USE_TZ        = True

# ── Static & Media ────────────────────────────────────────────────────
STATIC_URL   = '/static/'
STATIC_ROOT  = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = []
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── API docs ──────────────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'API',
    'DESCRIPTION': 'Production-ready Django REST API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

# ── Logging ───────────────────────────────────────────────────────────
import traceback


class CloudLoggingJSONFormatter(logging.Formatter):
    """
    Formats log records as JSON matching Cloud Logging's structured
    logging spec: https://cloud.google.com/logging/docs/structured-logging

    Key fields Cloud Logging recognizes natively:
      severity   -> drives the severity filter/color in Logs Explorer
      message    -> shown as the main log line
      logging.googleapis.com/sourceLocation -> file/line, shown in UI
    Everything else becomes part of jsonPayload, individually filterable
    in Logs Explorer with e.g. jsonPayload.tool="email_gen"
    """

    LEVEL_TO_SEVERITY = {
        'DEBUG':    'DEBUG',
        'INFO':     'INFO',
        'WARNING':  'WARNING',
        'ERROR':    'ERROR',
        'CRITICAL': 'CRITICAL',
    }

    def format(self, record):
        payload = {
            'severity': self.LEVEL_TO_SEVERITY.get(record.levelname, 'DEFAULT'),
            'message':  record.getMessage(),
            'logger':   record.name,
            'logging.googleapis.com/sourceLocation': {
                'file':     record.pathname,
                'line':     str(record.lineno),
                'function': record.funcName,
            },
        }

        # Attach any extra fields passed via logger.error(..., extra={...})
        # e.g. extra={'user_email': ..., 'event_type': ..., 'tool': ...}
        reserved = {
            'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
            'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
            'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
            'thread', 'threadName', 'processName', 'process', 'message',
            'taskName',
        }
        for key, value in record.__dict__.items():
            if key not in reserved:
                try:
                    json.dumps(value)  # only attach JSON-serializable extras
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)

        # Full stack trace — this is what makes Error Reporting pick it up
        if record.exc_info:
            payload['stack_trace'] = ''.join(traceback.format_exception(*record.exc_info))

        return json.dumps(payload, default=str)


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        'cloud_json': {
            '()': CloudLoggingJSONFormatter,
        },
    },

    'handlers': {
        # stdout — Cloud Run captures this automatically, no file needed
        'cloud_console': {
            'level':     'INFO',
            'class':     'logging.StreamHandler',
            'stream':    sys.stdout,
            'formatter': 'cloud_json',
        },
    },

    'root': {
        'handlers': ['cloud_console'],
        'level':    'INFO',
    },

    'loggers': {
        'django': {
            'handlers':  ['cloud_console'],
            'level':     'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers':  ['cloud_console'],
            'level':     'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers':  ['cloud_console'],
            'level':     'WARNING',
            'propagate': False,
        },
        'celery': {
            'handlers':  ['cloud_console'],
            'level':     'INFO',
            'propagate': False,
        },

        # All your apps — apps.tools.*, apps.subscriptions.*, apps.chatbot.*
        'apps': {
            'handlers':  ['cloud_console'],
            'level':     'INFO',
            'propagate': False,
        },

        # Quiet third-party noise down to WARNING so Logs Explorer isn't
        # flooded with every HTTP call these libraries make internally
        'stripe':  {'handlers': ['cloud_console'], 'level': 'WARNING', 'propagate': False},
        'urllib3': {'handlers': ['cloud_console'], 'level': 'WARNING', 'propagate': False},
        'openai':  {'handlers': ['cloud_console'], 'level': 'WARNING', 'propagate': False},
        'httpx':   {'handlers': ['cloud_console'], 'level': 'WARNING', 'propagate': False},
    },
}
