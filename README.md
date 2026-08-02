# Django Production Starter Kit

> Python 3.12 · Django 5.x · PostgreSQL · Redis · Celery · JWT · Docker · GitHub Actions
> 
> Built by [arhatinfo.com](https://arhatinfo.com) — Backend, AI Automation & Cloud Engineering

---

## Quick Reference

| URL | Description |
|-----|-------------|
| `http://localhost:8000` | Django app |
| `http://localhost:8000/admin/` | Admin panel |
| `http://localhost:8000/api/docs/` | Swagger UI |
| `http://localhost:8000/api/redoc/` | ReDoc |
| `http://localhost:8000/api/v1/core/health/` | Health check |
| `http://localhost:5555` | Flower (Celery dashboard) |

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [The .env File](#2-the-env-file)
3. [Running Locally (no Docker)](#3-running-locally-no-docker)
4. [Running with Docker](#4-running-with-docker)
5. [API Endpoints](#5-api-endpoints)
6. [GitHub Actions CI/CD](#6-github-actions-cicd)
7. [Production Deployment](#7-production-deployment)
8. [Common Errors & Fixes](#8-common-errors--fixes)
9. [Extending the Starter Kit](#9-extending-the-starter-kit)

---

## 1. Project Structure

```
django-production-starter/
├── apps/
│   ├── authentication/       # Custom User model, JWT auth, tests
│   └── core/                 # Base models, pagination, exceptions, health check
├── config/
│   ├── settings/
│   │   ├── base.py           # Shared settings (all environments)
│   │   ├── local.py          # Local development overrides
│   │   ├── staging.py        # Staging overrides
│   │   └── production.py     # Production (hardened security + Sentry)
│   ├── celery.py             # Celery app config
│   └── urls.py               # Root URL routing
├── docker/
│   └── Dockerfile            # Multi-stage build (local + production)
├── requirements/
│   ├── base.txt              # Installed in ALL environments
│   ├── local.txt             # Dev tools + flower + pytest
│   └── production.txt        # Gunicorn + health check
├── scripts/
│   └── wait_for_db.py        # Pure Python DB wait (no netcat needed)
├── .env.example              # Copy this to .env and fill in values
├── .github/workflows/ci.yml  # CI/CD pipeline
├── docker-compose.yml        # Local Docker setup
├── docker-compose.prod.yml   # Production overrides
├── manage.py
└── Makefile                  # Shortcut commands
```

---

## 2. The .env File

> **The only file you need to change.** Copy `.env.example` to `.env` before anything else.

```bash
cp .env.example .env
```

### Generate a SECRET_KEY

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Local (no Docker)

```env
DJANGO_SETTINGS_MODULE=config.settings.local
SECRET_KEY=any-long-random-string-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Use localhost — Django runs outside Docker
DATABASE_URL=postgres://postgres:postgres@localhost:5432/app_db
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

CORS_ALLOWED_ORIGINS=http://localhost:3000
USE_S3=False
SENTRY_DSN=
```

### Docker (local dev)

```env
DJANGO_SETTINGS_MODULE=config.settings.local
SECRET_KEY=any-long-random-string-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Use db and redis — Docker service hostnames
DATABASE_URL=postgres://postgres:postgres@db:5432/app_db
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

CORS_ALLOWED_ORIGINS=http://localhost:3000
USE_S3=False
SENTRY_DSN=
```

### Production

```env
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=very-long-random-50-plus-chars-string
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

DATABASE_URL=postgres://postgres:STRONG_PASSWORD@db:5432/app_db
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

CORS_ALLOWED_ORIGINS=https://yourdomain.com
SENTRY_DSN=https://your-key@sentry.io/project-id
USE_S3=True
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_STORAGE_BUCKET_NAME=your-bucket
AWS_S3_REGION_NAME=us-east-1
```

> **Key difference:** Local uses `localhost`, Docker uses `db` and `redis` as hostnames.

---

## 3. Running Locally (no Docker)

> Requires: Python 3.12, PostgreSQL, and Redis installed on your machine.

### Step 1 — Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### Step 2 — Install dependencies

```bash
pip install -r requirements/local.txt
```

### Step 3 — Configure .env

```bash
cp .env.example .env
# Set DATABASE_URL with @localhost:5432 (not @db:5432)
# Set a SECRET_KEY
```

### Step 4 — Create the database

```bash
# Mac (if postgres user does not exist)
createuser -s postgres
createdb -U postgres app_db

# Linux
sudo -u postgres psql -c "CREATE DATABASE app_db;"

# If you get 'role postgres does not exist' on Mac
psql postgres
# Inside psql:
CREATE ROLE postgres WITH SUPERUSER LOGIN PASSWORD 'postgres';
CREATE DATABASE app_db OWNER postgres;
\q
```

### Step 5 — Migrate and create superuser

```bash
python manage.py migrate
python manage.py createsuperuser
```

### Step 6 — Start the server

```bash
python manage.py runserver
```

Open `http://localhost:8000`

### Optional — Start Celery (3 extra terminal tabs)

```bash
# Tab 2 — Worker
celery -A config worker --loglevel=info

# Tab 3 — Beat (scheduled tasks)
celery -A config beat --loglevel=info

# Tab 4 — Flower dashboard (optional)
celery -A config flower --port=5555
```

---

## 4. Running with Docker

> Requires: Docker Desktop installed and running. Nothing else needed locally.

### Step 1 — Configure .env

```bash
cp .env.example .env
# DATABASE_URL must use @db:5432 (not localhost)
# REDIS_URL must use redis:6379 (not localhost)
# Set your SECRET_KEY
```

### Step 2 — Build and start

```bash
docker-compose build
docker-compose up -d
```

Migrations run automatically on startup. Wait ~10 seconds then open `http://localhost:8000`

### Step 3 — Create superuser

```bash
docker-compose exec web python manage.py createsuperuser
```

### Services

| Service | Description | Port |
|---------|-------------|------|
| `web` | Django development server | 8000 |
| `db` | PostgreSQL 16 | 5432 |
| `redis` | Redis 7 | 6379 |
| `celery` | Celery worker (async tasks) | — |
| `celery-beat` | Celery beat (scheduled tasks) | — |
| `flower` | Celery monitoring dashboard | 5555 |

### Common Docker commands

```bash
# See all running containers
docker-compose ps

# Follow logs
docker-compose logs -f
docker-compose logs -f web       # web only

# Open Django shell
docker-compose exec web python manage.py shell

# Open bash inside container
docker-compose exec web bash

# Stop all containers
docker-compose down

# Stop and wipe database (fresh start)
docker-compose down -v

# Rebuild from scratch (after adding packages)
docker-compose build --no-cache
docker-compose up -d

# Restart one service
docker-compose restart web
```

### Makefile shortcuts

```bash
make build        # Build Docker images
make up           # Start all services
make down         # Stop all services
make down-v       # Stop and wipe database
make logs         # Follow all logs
make shell        # Django shell
make migrate      # Run migrations
make superuser    # Create admin user
make test         # Run tests
make test-cov     # Tests with coverage report
```

---

## 5. API Endpoints

### Authentication

All protected endpoints require:
```
Authorization: Bearer <access_token>
```

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/register/` | No | Register — returns tokens immediately |
| POST | `/api/v1/auth/token/` | No | Login — returns access + refresh tokens |
| POST | `/api/v1/auth/token/refresh/` | No | Refresh access token |
| POST | `/api/v1/auth/token/verify/` | No | Verify a token |
| POST | `/api/v1/auth/logout/` | Yes | Logout — blacklists refresh token |
| GET/PATCH | `/api/v1/auth/me/` | Yes | Get or update profile |
| PUT | `/api/v1/auth/me/password/` | Yes | Change password |
| GET | `/api/v1/core/health/` | No | Health check (DB + Redis) |

### Auth flow

```bash
# Register
POST /api/v1/auth/register/
{
  "email": "user@example.com",
  "first_name": "Jane",
  "last_name": "Smith",
  "password": "StrongPass123!",
  "password2": "StrongPass123!"
}
# → { "user": {...}, "tokens": { "access": "eyJ...", "refresh": "eyJ..." } }

# Login
POST /api/v1/auth/token/
{ "email": "user@example.com", "password": "StrongPass123!" }
# → { "access": "eyJ...", "refresh": "eyJ..." }

# Use access token (valid 60 min by default)
GET /api/v1/auth/me/
Authorization: Bearer eyJ...

# Refresh when expired
POST /api/v1/auth/token/refresh/
{ "refresh": "eyJ..." }
# → { "access": "eyJ...", "refresh": "eyJ..." }

# Logout
POST /api/v1/auth/logout/
{ "refresh": "eyJ..." }
# → 205 Reset Content
```

### Error response format

All errors return a consistent envelope:

```json
{
  "success": false,
  "error": {
    "code": "not_found",
    "message": "Not found.",
    "detail": { ... }
  }
}
```

---

## 6. GitHub Actions CI/CD

### What the pipeline does

1. Spins up PostgreSQL + Redis as test services
2. Installs `requirements/local.txt`
3. Runs `python manage.py migrate`
4. Runs `pytest --cov=apps` with coverage
5. On `main` branch: builds Docker image

### Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "initial commit"

# Create repo on github.com, then:
git remote add origin https://github.com/yourusername/your-repo.git
git push -u origin main
```

Go to your repo → **Actions** tab → watch it run live.

### Step 2 — Add deployment secrets

GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret | Value |
|--------|-------|
| `PROD_HOST` | Your server IP address |
| `PROD_USER` | SSH username (usually `ubuntu`) |
| `PROD_SSH_KEY` | Your private SSH key (`cat ~/.ssh/id_rsa`) |

### Run CI locally without pushing

```bash
# Install act
brew install act          # Mac
choco install act-cli     # Windows

# Run full CI
act

# Run test job only
act -j test
```

### Run tests directly (fastest)

```bash
# Outside Docker
pytest -v
pytest --cov=apps --cov-report=term-missing

# Inside Docker
docker-compose exec web pytest -v
make test-cov
```

---

## 7. Production Deployment

### Step 1 — Server setup (Ubuntu 22.04)

```bash
ssh ubuntu@YOUR_SERVER_IP

# Install Docker
sudo apt update
sudo apt install docker.io docker-compose -y
sudo systemctl enable docker
sudo usermod -aG docker ubuntu

# Log out and back in for group change to take effect
exit
ssh ubuntu@YOUR_SERVER_IP
```

### Step 2 — Copy project to server

```bash
# Option A — clone from GitHub (recommended)
git clone https://github.com/yourusername/your-repo.git /opt/app
cd /opt/app

# Option B — rsync from local machine
rsync -avz ./ ubuntu@YOUR_SERVER_IP:/opt/app/
```

### Step 3 — Configure production .env

```bash
cd /opt/app
cp .env.example .env
nano .env

# Critical values:
# DJANGO_SETTINGS_MODULE=config.settings.production
# DEBUG=False
# SECRET_KEY=very-long-random-string
# ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
# SENTRY_DSN=https://...
```

### Step 4 — Deploy

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Create superuser
docker-compose exec web python manage.py createsuperuser
```

### Step 5 — Nginx reverse proxy

```bash
sudo apt install nginx -y
sudo nano /etc/nginx/sites-available/app
```

Paste this config:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    location /static/ { alias /opt/app/staticfiles/; }
    location /media/  { alias /opt/app/media/; }
    client_max_body_size 20M;
}
```

```bash
sudo ln -s /etc/nginx/sites-available/app /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Step 6 — HTTPS with Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

---

## 8. Common Errors & Fixes

| Error | Fix |
|-------|-----|
| `No module named 'debug_toolbar'` | `pip install -r requirements/local.txt` |
| `No module named 'django_extensions'` | `pip install -r requirements/local.txt` |
| `No module named 'whitenoise'` | `pip install -r requirements/base.txt` |
| `No module named 'flower'` | `pip install flower` then run via `celery -A config flower` |
| `No such command 'flower'` | Run as `celery -A config flower --port=5555` not `flower` alone |
| `nc: not found` | Already fixed — uses `scripts/wait_for_db.py` (pure Python) |
| `relation does not exist` | `python manage.py migrate` or `docker-compose exec web python manage.py migrate` |
| `role "postgres" does not exist` | `createuser -s postgres` (Mac/Homebrew) |
| `ALLOWED_HOSTS DisallowedHost` | Add domain/IP to `ALLOWED_HOSTS` in `.env` |
| `CORS blocked` | Add frontend URL to `CORS_ALLOWED_ORIGINS` in `.env` |
| `Port 8000 already in use` | Change to `8001:8000` in `docker-compose.yml` |
| `No migrations to apply` | Not an error — database is already up to date |
| `staticfiles W004 warning` | Not an error — create a `/static` folder or ignore it |
| `SECRET_KEY not set` | Generate one — see [The .env File](#2-the-env-file) section |
| `Gunicorn listening on 127.0.0.1` | Use `runserver` for local Docker, gunicorn only in production |

---

## 9. Extending the Starter Kit

### Add a new app

```bash
# Create the app
python manage.py startapp myapp apps/myapp

# Register in config/settings/base.py
LOCAL_APPS = [
    'apps.core',
    'apps.authentication',
    'apps.myapp',          # add here
]

# Create and run migrations
python manage.py makemigrations
python manage.py migrate
```

### Use the base model

All models should inherit from `TimeStampedModel` for automatic UUID, `created_at`, `updated_at`:

```python
from apps.core.models import TimeStampedModel

class Invoice(TimeStampedModel):
    # id, created_at, updated_at inherited automatically
    vendor = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date   = models.DateField()
```

For soft-delete support:

```python
from apps.core.models import SoftDeleteModel

class Document(SoftDeleteModel):
    title = models.CharField(max_length=255)
    # adds is_deleted, deleted_at, .soft_delete(), .restore()
```

### Use the logger

```python
import logging
logger = logging.getLogger(__name__)

logger.info('Invoice processed: %s', invoice.id)
logger.warning('Low confidence score: %s', score)
logger.error('Failed to push to accounting system', exc_info=True)
```

### Add a Celery task

```python
# apps/myapp/tasks.py
from config.celery import app

@app.task(bind=True, max_retries=3)
def process_invoice(self, invoice_id):
    try:
        # your logic here
        pass
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

# Call it anywhere:
process_invoice.delay(invoice_id)

# Schedule it in Django admin → Periodic Tasks (Celery Beat)
```

---

## Environment Comparison

| Setting | Local | Docker | Production |
|---------|-------|--------|------------|
| `SETTINGS_MODULE` | `config.settings.local` | `config.settings.local` | `config.settings.production` |
| `DEBUG` | `True` | `True` | `False` |
| DB hostname | `localhost` | `db` | `db` |
| Redis hostname | `localhost` | `redis` | `redis` |
| Email backend | Console (prints to terminal) | Console | Real SMTP |
| CORS | Allow all origins | Allow all origins | Listed origins only |
| Sentry | Off | Off | On (when DSN set) |
| Password hasher | Default | Default | Argon2 (most secure) |
| Static files | WhiteNoise | WhiteNoise | WhiteNoise or S3 |
| Debug toolbar | Yes (if installed) | Yes (if installed) | No |

---

## Built by arhatinfo.com

Backend, AI automation & cloud engineering — production-ready systems built to scale from day one.

- Website: [arhatinfo.com](https://arhatinfo.com)
- Email: [hello@arhatinfo.com](mailto:contact@arhatinfo.com)
- Upwork: Available for projects
