from .base import *  # noqa

DEBUG = True

# ── Only add optional dev tools if they are installed ─────────────────
try:
    import debug_toolbar  # noqa
    INSTALLED_APPS += ['debug_toolbar']  # noqa
    MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE  # noqa
    INTERNAL_IPS = ['127.0.0.1']
except ImportError:
    pass

try:
    import django_extensions  # noqa
    INSTALLED_APPS += ['django_extensions']  # noqa
except ImportError:
    pass


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
    'django-backend-dev-xzkib7kizq-uk.a.run.app',
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
    'https://dev-hosting.arhat.info',
    'https://localhost:3000',
]
CORS_ALLOW_CREDENTIALS = True

# Security
SECURE_SSL_REDIRECT            = False   # API Gateway handles SSL
SESSION_COOKIE_SECURE          = True
CSRF_COOKIE_SECURE             = True
SECURE_HSTS_SECONDS            = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# ── Email: print to console ───────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

# ── Relax CORS in dev ─────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000'
]


