.PHONY: help build up down restart logs shell migrate makemigrations createsuperuser test lint format collectstatic celery-worker celery-beat flower

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Docker ────────────────────────────────────────────────────────────
build: ## Build all Docker images
	docker-compose build

up: ## Start all services
	docker-compose up -d

up-logs: ## Start all services and follow logs
	docker-compose up

down: ## Stop all services
	docker-compose down

restart: ## Restart all services
	docker-compose restart

logs: ## Follow logs from all containers
	docker-compose logs -f

logs-web: ## Follow web container logs
	docker-compose logs -f web

# ── Django ────────────────────────────────────────────────────────────
shell: ## Open Django shell in web container
	docker-compose exec web python manage.py shell_plus

bash: ## Open bash in web container
	docker-compose exec web bash

migrate: ## Run database migrations
	docker-compose exec web python manage.py migrate --noinput

makemigrations: ## Create new migrations
	docker-compose exec web python manage.py makemigrations

createsuperuser: ## Create a Django superuser
	docker-compose exec web python manage.py createsuperuser

collectstatic: ## Collect static files
	docker-compose exec web python manage.py collectstatic --noinput

# ── Testing ───────────────────────────────────────────────────────────
test: ## Run all tests
	docker-compose exec web pytest

test-cov: ## Run tests with coverage report
	docker-compose exec web pytest --cov=apps --cov-report=html --cov-report=term-missing

test-auth: ## Run authentication tests only
	docker-compose exec web pytest apps/authentication/tests.py -v

test-core: ## Run core tests only
	docker-compose exec web pytest apps/core/tests.py -v

# ── Code quality ──────────────────────────────────────────────────────
lint: ## Run flake8 linter
	docker-compose exec web flake8 .

format: ## Format code with black + isort
	docker-compose exec web black .
	docker-compose exec web isort .

format-check: ## Check formatting without writing changes
	docker-compose exec web black --check .
	docker-compose exec web isort --check-only .

# ── Celery ────────────────────────────────────────────────────────────
celery-worker: ## Start Celery worker locally (outside Docker)
	celery -A config worker --loglevel=info --concurrency=4

celery-beat: ## Start Celery beat locally (outside Docker)
	celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler

flower: ## Open Flower dashboard
	open http://localhost:5555

# ── Local dev (without Docker) ────────────────────────────────────────
install: ## Install local dependencies
	pip install -r requirements/local.txt

runserver: ## Run Django dev server locally
	python manage.py runserver 0.0.0.0:8000

# ── Database ──────────────────────────────────────────────────────────
dbshell: ## Open database shell
	docker-compose exec web python manage.py dbshell

flush: ## Flush all database data (CAUTION)
	docker-compose exec web python manage.py flush --noinput

reset-db: ## Drop and recreate the database (CAUTION - dev only)
	docker-compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS app_db;"
	docker-compose exec db psql -U postgres -c "CREATE DATABASE app_db;"
	$(MAKE) migrate
