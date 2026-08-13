# Tylented — Backend

> Tylented — AI-powered career automation platform

[Live Demo](https://dev.arhat.info/api/docs) · [Website](https://dev-hosting.arhat.info/) · [Architecture](#architecture)

---

## Why I Built This

Job searching is repetitive: tailoring a resume, writing a cover letter, answering a recruiter, matching a JD against your background. I built Tylented to automate that work — a Django REST API backend, a React frontend, and a Chrome extension that plugs AI tools directly into the browser while someone is applying. This repo is the backend: the API, billing, auth, and AI integration layer that the frontend and extension both call.

It's a real product with paying users on Stripe, not a tutorial project — which shaped a lot of the decisions below (rate limiting AI usage per plan, webhook signature verification, environment-isolated infrastructure).

---

## Architecture

```
                    ┌───────────────┐        ┌──────────────────────┐
                    │   React SPA   │        │  Chrome Extension     │
                    │               │        │  (Manifest V3)        │
                    └───────┬───────┘        └───────────┬───────────┘
                            │                             │
                            │        JWT Bearer auth      │
                            └──────────────┬──────────────┘
                                           ▼
                          ┌─────────────────────────────────┐
                          │        Django REST API           │
                          │   (Gunicorn on Cloud Run)         │
                          │                                   │
                          │  • JWT auth (rotation + blacklist)│
                          │  • Feature-flag permission layer  │
                          │  • drf-spectacular (OpenAPI docs) │
                          │  • Structured JSON logging         │
                          │  • Sentry error tracking           │
                          └──┬───────────┬───────────┬────────┘
                             │           │           │
                 ┌───────────▼──┐  ┌─────▼─────┐  ┌──▼──────────────┐
                 │  PostgreSQL   │  │  OpenAI    │  │  Stripe          │
                 │  (Cloud SQL,  │  │  GPT-4o /  │  │  Checkout +      │
                 │  private IP   │  │  4o-mini   │  │  signed webhooks │
                 │  via VPC)     │  └────────────┘  └──────────────────┘
                 └───────┬───────┘
                         │
                 ┌───────▼────────────────┐
                 │  Celery + Redis         │
                 │  (async tasks, beat     │
                 │   scheduler, Flower)    │
                 └─────────────────────────┘

CI/CD: GitHub Actions → Cloud Build → Cloud Run deploy
       → Cloud Run Job (migrations, run separately from the deploy)
       → Direct VPC egress restricts prod DB access to a private IP
```

Key decisions baked into this diagram, not just boxes:

- **Migrations run as a separate Cloud Run Job, not inline with deploy.** If a migration fails, it doesn't take the running revision down with it.
- **The database has no public entry point in production.** Cloud Run reaches Cloud SQL over Direct VPC egress restricted to private ranges only — the API is the only thing that can talk to Postgres.
- **The AI layer sits behind the API, not in front of it.** The frontend and extension never call OpenAI directly; every AI call goes through the Django service layer so tier gating, rate limiting, and logging apply uniformly.

---

## Engineering

- **Backend**: Django 5.0 + Django REST Framework, split into focused apps (`authentication`, `resumes`, `subscriptions`, `tools`, `chatbot`, `core`) instead of one monolithic app. A shared `TimeStampedModel`/pagination/exception-handler base in `core` keeps the others consistent.
- **API architecture**: versioned under `/api/`, self-documenting via `drf-spectacular` (Swagger UI + ReDoc generated from the code, not hand-maintained), consistent error envelope (`{success, error: {code, message, detail}}`) returned by a single custom exception handler instead of ad-hoc error shapes per view.
- **PostgreSQL**: Cloud SQL, environment-specific settings modules (`local` / `development` / `staging` / `production`) so local dev, staging, and prod never share config by accident. Production isolates the DB behind a private IP (see Infrastructure).
- **LLM integration**: OpenAI GPT-4o and GPT-4o-mini, routed per-tool by a model map — cheaper `gpt-4o-mini` for straightforward generation (emails, LinkedIn posts), `gpt-4o` reserved for tasks that need real reasoning (job matching, cover letters). Resume text extraction falls back through `pdfplumber` → `pypdf` → `python-docx` so a PDF that trips up one parser still gets read instead of failing the upload outright.
- **Authentication**: JWT via `djangorestframework-simplejwt`, rotating refresh tokens with blacklist-after-rotation (a stolen refresh token can't be replayed after the legitimate client rotates it). Authorization is **feature-flag based**, not a strict tier ladder — a plan can independently grant "removes ads," "AI tools access," or "Chrome extension access," so pricing tiers can mix capabilities without new permission classes. A separate API-key auth path exists for programmatic access.
- **Cloud infrastructure**: Cloud Run (containerized, autoscaling, scale-to-zero), Cloud SQL Postgres reached over Direct VPC egress, environment-scoped deploys — pushes to `main` deploy to production with its own GCP secrets/variables, pushes to `develop` deploy to a separate development service.
- **CI/CD**: GitHub Actions builds the image via Cloud Build, deploys to Cloud Run, then runs `manage.py migrate` as its own Cloud Run Job — deploy and migrate are decoupled on purpose.
- **Observability**: Sentry for exception tracking, plus a custom logging formatter that emits Cloud Logging-native structured JSON (severity, source location, and full stack traces mapped to the fields Cloud Logging's Error Reporting expects) instead of plain-text logs that are hard to query in production.

---

## AI Architecture

Nine+ AI-powered endpoints (cover letters, resume summaries, job-description matching, recruiter replies, LinkedIn posts, SQL/regex/cron generation, API request analysis) share one service layer (`gpt_service.py`) and one decorator (`ai_tool_endpoint`) instead of each view reimplementing auth, quota, and logging:

- **Tier + quota enforcement in one place.** The decorator checks the caller's subscription tier, then their remaining daily AI quota (tracked per user/day via a rolling counter), before the request is allowed to reach OpenAI — a request that fails the quota check never gets logged as a "used" AI call or costs an API token.
- **Every call is logged**, success or failure — token counts, model used, duration, and a preview of the output — both for per-user audit history and for the daily counters that drive rate limiting.
- **Bad input fails cheap.** A `ValueError` from the view (missing required field, etc.) returns a 400 without touching OpenAI or the quota; only real model/API failures are logged as failed AI calls.

### AI Engineering

The application uses LLMs as a component of the application architecture rather than as an uncontrolled source of business logic. Every AI call is centralized behind a single service layer rather than called ad hoc from views, so tier gating, rate limiting, and logging apply uniformly. Where an AI response feeds downstream logic — resume parsing into structured skills/experience/achievements — the model is constrained to OpenAI's structured JSON output mode and the response is parsed and validated (`json.loads` with a safe empty-object fallback) before it's persisted, rather than trusted as-is.

*Honest gap, not glossed over:* there's no automated eval harness yet that regression-tests prompt changes against a fixed set of representative inputs — today that verification is manual. It's the next thing I'd add before touching the resume-parsing prompt again.

---

## Reliability & Testing

- Django `TestCase` coverage exists for the `authentication` and `core` apps; `resumes`, `subscriptions`, `tools`, and `chatbot` don't have automated test coverage yet — the honest state of it, not oversold.
- `django-health-check` exposes `/api/core/health/`, checking DB and Redis connectivity — used for uptime checks.
- Sentry captures unhandled exceptions in staging and production with full stack traces.
- Stripe webhook handling verifies the signature on every incoming event (`construct_webhook_event`) before trusting the payload, and reconciles local subscription state against Stripe on read if the two ever drift (e.g. a missed webhook), rather than silently trusting a possibly-stale local row.

---

## Security

- All secrets are loaded from environment variables via `python-decouple` — nothing is hardcoded, and `SECRET_KEY`/API keys/DB credentials have no default fallback in code, so the app refuses to start without them configured.
- `.env` and `.env.*` are gitignored; verified via full git history (`git log --all --full-history`) that no env file has ever been committed to this repo.
- `.env.example` ships placeholder values only — see below.
- JWT access tokens are short-lived, refresh tokens rotate and are blacklisted after use.
- Authorization is enforced at the DRF permission-class layer (server-side), not just hidden in the frontend.
- Stripe webhooks are signature-verified before being processed.
- Production settings enable `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, and a one-year `SECURE_HSTS_SECONDS` with subdomains included; `CORS_ALLOWED_ORIGINS` and `ALLOWED_HOSTS` are explicit allowlists per environment, not wildcards.

**Bad (what NOT to do — a real secret value in a file that looks like a template):**
```env
OPENAI_API_KEY=sk-proj-a1B2c3D4e5F6...
```

**Good (what this repo actually does — `.env.example` is placeholders only):**
```env
OPENAI_API_KEY=<openai-api-key>
```

---

## Infrastructure

- **Compute**: Google Cloud Run — separate services for `production` (branch `main`) and `development` (branch `develop`), each with its own environment variables and secrets.
- **Database**: Cloud SQL for PostgreSQL. Production reaches it over Direct VPC egress (`--vpc-egress=private-ranges-only`) so the database is not exposed on a public IP to the API layer.
- **Async work**: Celery workers + beat scheduler backed by Redis, with Flower available for queue monitoring.
- **Static/media**: WhiteNoise for static files by default, with optional S3 (`django-storages` + `boto3`) for production media.
- **Containers**: multi-stage Docker build (separate build/runtime stages, non-root user, only runtime system deps in the final image) run via Gunicorn.

---

## Development Workflow

- Environment-specific Django settings modules (`local`, `development`, `staging`, `production`) instead of one settings file branching on flags.
- `docker-compose.yml` for local Postgres/Redis/Celery/Flower; the API can also run directly against a local or Dockerized Postgres.
- GitHub Actions CI/CD: push to `develop` deploys to the development Cloud Run service, push to `main` deploys to production — each with its own scoped GCP service account, secrets, and (for production) VPC configuration.
- API contract is generated from code (`drf-spectacular`) and browsable at `/api/docs/` — the schema can't drift from the implementation the way a hand-written API doc can.

---

## Running Locally

```bash
git clone https://github.com/rohit-jain-058/arhat-info-django-backend.git
cd arhat-info-django-backend
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements/local.txt

cp .env.example .env
# fill in: SECRET_KEY, OPENAI_API_KEY, STRIPE_* keys, DB_* — all placeholders in .env.example

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Optional — Celery, if you're touching async tasks:
```bash
celery -A config worker --loglevel=info
celery -A config beat --loglevel=info
celery -A config flower --port=5555
```

API docs once running: `http://localhost:8000/api/docs/`

---

## What I Learned

- Feature-flag permissions scale better than tier ladders the moment pricing stops being strictly linear — I hit this rebuilding the permission classes when "removes ads" and "AI tools access" stopped being the same axis.
- Decoupling migrations from deploy (a separate Cloud Run Job instead of running them inline) turned a "bad migration takes the whole service down" failure mode into a "the job fails, the running revision is untouched" one.
- Centralizing every AI call behind one decorator instead of repeating auth/quota/logging per view meant adding tier gating to a Chrome extension surface later was a one-line permission check, not a rewrite.
- Structured JSON output mode from the model isn't optional if a downstream system is going to parse the response — validating and falling back beats trusting raw text every time.
