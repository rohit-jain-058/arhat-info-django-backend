# ── Build stage ───────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/

# Accept BUILD_ENV as build arg — defaults to development
ARG BUILD_ENV=development
ENV BUILD_ENV=${BUILD_ENV}
RUN pip install --prefix=/install -r requirements/${BUILD_ENV}.txt


# ── Runtime stage ─────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Accept DJANGO_SETTINGS_MODULE as build arg
# Can also be overridden at runtime via Cloud Run env vars
ARG DJANGO_SETTINGS_MODULE=config.settings.development
ENV DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE}

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r django && useradd -r -g django django

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=django:django . .

RUN mkdir -p /app/staticfiles /app/media \
    && chown -R django:django /app

USER django

EXPOSE 8080

CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "4", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]