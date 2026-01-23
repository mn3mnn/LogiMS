# LogiMS Backend

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.2.6-green.svg)](https://www.djangoproject.com/)
[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)

Django REST API backend for the LogiMS (Logistics Management System) platform. Provides comprehensive APIs for managing drivers, trips, payroll, documents, and notifications.

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Development Setup](#development-setup)
- [Database Management](#database-management)
- [Celery Setup](#celery-setup)
- [Running the Server](#running-the-server)
- [API Documentation](#api-documentation)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Management Commands](#management-commands)
- [Troubleshooting](#troubleshooting)

## Overview

LogiMS Backend is a Django REST Framework-based API that powers the logistics management system. It provides:

- **RESTful API** for all frontend operations
- **Asynchronous task processing** with Celery
- **Document processing** for payments, trips, invoices, and contracts
- **Notification system** for document expiration alerts
- **Multi-tenant support** with company-based data isolation
- **Comprehensive data models** for drivers, trips, payroll, and more

## Tech Stack

### Core Framework
- **Django 5.2.6** - Web framework
- **Python 3.13** - Programming language
- **Django REST Framework 3.16.1** - API framework
- **DRF Spectacular 0.28.0** - OpenAPI/Swagger documentation

### Database & Cache
- **PostgreSQL** - Primary database (via psycopg)
- **Redis 6.4.0** - Caching and Celery message broker

### Task Queue
- **Celery 5.5.3** - Asynchronous task processing
- **Celery Beat 2.8.1** - Scheduled task scheduler
- **Flower 2.0.1** - Celery monitoring

### Authentication & Security
- **Django Allauth 65.11.2** - Authentication with MFA support
- **Argon2** - Password hashing
- **CORS Headers** - Cross-origin resource sharing

### Storage
- **Django Storages** - S3/R2 cloud storage support
- **WhiteNoise** - Static file serving

### Email
- **Django Anymail 13.1** - Hostinger email integration

### Package Management
- **UV** - Fast Python package manager


## Project Structure

```
logims/
├── config/                      # Django configuration
│   ├── settings/               # Environment-specific settings
│   │   ├── base.py            # Base settings
│   │   ├── local.py           # Local development settings
│   │   ├── production.py      # Production settings
│   │   └── test.py            # Test settings
│   ├── api_router_v1.py       # API route definitions
│   ├── celery_app.py          # Celery configuration
│   ├── urls.py                # URL routing
│   ├── wsgi.py                # WSGI application
│   └── asgi.py                # ASGI application
│
├── logims/                     # Application modules
│   ├── companies/             # Company management
│   ├── drivers/               # Driver management & documents
│   ├── trips/                 # Trip tracking & records
│   ├── payroll/               # Payroll & payment processing
│   ├── uploads/               # Document upload system
│   ├── notifications/         # Notification system
│   ├── orders/                # Order management
│   ├── users/                 # User management
│   └── contrib/               # Shared utilities
│
├── compose/                    # Docker compose configurations
│   ├── local/                 # Local development Dockerfiles
│   └── production/            # Production Dockerfiles
│
├── tests/                      # Test suite
├── locale/                     # Internationalization files
├── docs/                       # Documentation
├── logs/                       # Application logs
├── manage.py                   # Django management script
├── pyproject.toml             # Project configuration & dependencies
└── docker-compose.local.yml    # Local Docker Compose config
```

## Environment Setup

### Environment Files

Environment variables are stored in `.envs/` directory:

```
.envs/
├── .local/
│   ├── .django        # Django settings
│   └── .postgres      # PostgreSQL connection
└── .production/
    ├── .django        # Production Django settings
    └── .postgres      # Production PostgreSQL connection
```

### Required Environment Variables

#### `.envs/.local/.django`
```bash
# Django Core
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database (or use DATABASE_URL)
DATABASE_URL=postgres://logims:password@postgres:5432/logims

# Redis
REDIS_URL=redis://redis:6379/0

# Email (optional for local)
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=your-sendgrid-api-key
DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# Storage (optional - uses local by default)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_STORAGE_BUCKET_NAME=
AWS_S3_ENDPOINT_URL=  # For Cloudflare R2
```

#### `.envs/.local/.postgres`
```bash
POSTGRES_DB=logims
POSTGRES_USER=logims
POSTGRES_PASSWORD=password
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

## Development Setup

### Option 1: Docker (Recommended)

1. **Build and start services**
   ```bash
   docker compose -f docker-compose.local.yml build
   docker compose -f docker-compose.local.yml run --rm django uv lock
   docker compose -f docker-compose.local.yml up --build
   ```

2. **Run migrations**
   ```bash
   docker compose -f docker-compose.local.yml run --rm django python manage.py migrate
   ```

3. **Create superuser**
   ```bash
   docker compose -f docker-compose.local.yml run --rm django python manage.py createsuperuser
   ```

4. **Access services**
   - API: http://localhost:8000/api/v1
   - Admin: http://localhost:8000/admin
   - API Docs: http://localhost:8000/api/docs/
   - Flower (Celery): http://localhost:5555


## Database Management

### Creating Migrations
```bash
# Create migrations for all apps With Docker
docker compose -f docker-compose.local.yml run --rm django python manage.py makemigrations
```

### Applying Migrations
```bash
docker compose -f docker-compose.local.yml run --rm django python manage.py migrate
```

### Database Shell
```bash
docker compose -f docker-compose.local.yml run --rm django python manage.py dbshell
```

### Django Shell
```bash
docker compose -f docker-compose.local.yml run --rm django python manage.py shell
```

### Create database backup
```bash
docker compose -f docker-compose.local.yml run --rm django python manage.py dumpdata > backup.json
```

### Load database backup
```bash
docker compose -f docker-compose.local.yml run --rm django python manage.py loaddata backup.json
```

## Celery Setup

### Running Celery Worker

**With Docker:**
```bash
# Celery worker is automatically started in docker-compose.local.yml
docker compose -f docker-compose.local.yml up celeryworker
```

### Running Celery Beat (Scheduled Tasks)

**With Docker:**
```bash
# Celery beat is automatically started in docker-compose.local.yml
docker compose -f docker-compose.local.yml up celerybeat
```

### Monitoring with Flower
```bash
# With Docker (already configured)
docker compose -f docker-compose.local.yml up flower
```

Access Flower at: http://localhost:5555

## Running the Server

### Development Server
```bash
docker compose -f docker-compose.local.yml up django
```

### Production Server (Gunicorn)
```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

### With Uvicorn (for WebSocket support)
```bash
uvicorn config.asgi:application --host 0.0.0.0 --port 8000
```

## API Documentation

### Interactive API Documentation

When running the development server, access interactive API documentation:

- **Swagger UI**: http://localhost:8000/api/docs/
- **ReDoc**: http://localhost:8000/api/schema/redoc/
- **OpenAPI Schema**: http://localhost:8000/api/schema/

### API Endpoints

The API is versioned at `/api/v1/`. Main endpoints include:

- `/api/v1/users/` - User management
- `/api/v1/drivers/` - Driver management
- `/api/v1/supervisors/` - Supervisor management
- `/api/v1/companies/` - Company management
- `/api/v1/uploads/` - Document uploads
- `/api/v1/tags/` - Tag management
- `/api/v1/payroll/records/` - Payment records
- `/api/v1/trips/records/` - Trip records

### Authentication

The API uses token-based authentication:

```bash
# Obtain token
POST /api/auth-token/
{
  "username": "your_username",
  "password": "your_password"
}

# Use token in requests
Authorization: Token <your-token>
```

## Testing

### Run All Tests
```bash
uv run pytest

# With Docker
docker compose -f docker-compose.local.yml run --rm django uv run pytest
```

### Run Tests with Coverage
```bash
uv run coverage run -m pytest
uv run coverage html
uv run open htmlcov/index.html  # View coverage report
```

### Run Specific Test
```bash
uv run pytest logims/drivers/tests/test_models.py
```

### Run Tests for Specific App
```bash
uv run pytest logims/drivers/
```

### Static Files
```bash
# Collect static files
python manage.py collectstatic --noinput
```

### Translations
```bash
# Create translation files
python manage.py makemessages -l de
python manage.py makemessages -l fr
python manage.py makemessages -l pt_BR

# Compile translations
python manage.py compilemessages
```

## Troubleshooting

### Database Connection Issues

**Problem**: Cannot connect to PostgreSQL
```bash
# Check if PostgreSQL is running
docker compose -f docker-compose.local.yml ps postgres

# Check database URL in .envs/.local/.django
# Ensure DATABASE_URL matches your PostgreSQL setup
```

### Redis Connection Issues

**Problem**: Celery tasks not running
```bash
# Check if Redis is running
docker compose -f docker-compose.local.yml ps redis

# Test Redis connection
docker compose -f docker-compose.local.yml run --rm django python -c "import redis; r = redis.from_url('redis://redis:6379/0'); print(r.ping())"
```

## Additional Resources

- [Django Documentation](https://docs.djangoproject.com/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [Celery Documentation](https://docs.celeryq.dev/)
- [Cookiecutter Django](https://cookiecutter-django.readthedocs.io/)

## License

This project is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details.

Copyright (c) 2025 Monem Tarek
