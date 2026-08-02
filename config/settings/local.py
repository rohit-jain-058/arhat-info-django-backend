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

# ── Email: print to console ───────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

# ── Relax CORS in dev ─────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True


