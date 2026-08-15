from .base import *
import os

DEBUG = False

# Lambda sets AWS_LAMBDA_FUNCTION_NAME in the environment
IS_LAMBDA = bool(os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))

# Allowed hosts — add your API Gateway URL and custom domain
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    'api.arhatinfo.com',                        # your custom domain
    'prod.arhat.info',
    'prod.tylented.com',
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
    'https://*.arhat.info',
    'https://arhatinfo.com',
    'https://www.arhatinfo.com',
    'https://www.tylented.com',
    'https://tylented.com'
        

]
CORS_ALLOW_CREDENTIALS = True

# Security
SECURE_SSL_REDIRECT            = False   # API Gateway handles SSL
SESSION_COOKIE_SECURE          = True
CSRF_COOKIE_SECURE             = True
SECURE_HSTS_SECONDS            = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
