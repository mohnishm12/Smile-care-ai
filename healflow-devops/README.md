# HealFlow AI — DevOps Infrastructure

## Overview
This directory contains all infrastructure, deployment, and monitoring configurations for HealFlow AI — an enterprise-grade omnichannel patient communication platform.

The application code lives alongside this directory:

```
Smile-care-ai/
├── .github/workflows/        # GitHub Actions pipelines (must live here to run)
│   ├── backend-ci.yml        # Backend lint, type-check, test, scan, push
│   ├── frontend-ci.yml       # Frontend lint, type-check, build, scan, push
│   └── infrastructure-ci.yml # Terraform fmt/validate/plan/apply
├── healflow-backend/         # FastAPI + Celery application
│   ├── src/                  # Application code (config, models, routers, tasks)
│   ├── alembic/              # Database migrations
│   └── tests/                # Pytest suite
├── healflow-frontend/        # Next.js 15 application (App Router, standalone)
└── healflow-devops/          # ← this directory
```

## Directory Structure

```
healflow-devops/
├── .env.example              # Environment variable template
├── README.md                 # This file
├── docker-compose.yml        # Production-shaped orchestration (nginx-only exposure)
├── docker-compose.dev.yml    # Dev overlay — publishes DB/API/metrics ports
├── docker/                   # Dockerfiles for all services
│   ├── Dockerfile.backend    # FastAPI backend (multi-stage, incl. alembic)
│   ├── Dockerfile.frontend   # Next.js standalone server (node runtime)
│   ├── Dockerfile.celery     # Celery worker/beat
│   └── Dockerfile.*.dockerignore  # Per-Dockerfile build context excludes
├── terraform/                # AWS baseline (ECR repos + lifecycle policies)
├── nginx/                    # Reverse proxy configuration
│   ├── nginx.conf            # Main config: security headers, rate limits, gzip
│   ├── default.conf          # Virtual host: TLS, routing, WebSocket upgrade
│   └── ssl/                  # TLS certs (gitignored — generate or provision)
├── monitoring/               # Observability stack
│   ├── prometheus/           # Scrape configs + alert rules
│   ├── grafana/              # Datasource + pre-built dashboards
│   └── otel/                 # OpenTelemetry collector config
├── security/                 # HIPAA compliance + security headers docs
└── scripts/
    ├── generate-dev-certs.sh # Self-signed TLS for local dev (run once)
    ├── init-db.sql           # Postgres init: extensions, schema, roles
    ├── run-migrations.sh     # Alembic runner (used by `migrate` service)
    └── healthcheck-backend.sh
```

## Quick Start

### Prerequisites
- Docker 24+ and Docker Compose v2+
- Git

### Development Environment
```bash
# Clone the repository
git clone https://github.com/mohnishm12/Smile-care-ai.git
cd Smile-care-ai

# 1. Environment configuration (compose reads healflow-devops/.env)
cp healflow-devops/.env.example healflow-devops/.env
#    Edit healflow-devops/.env — set real JWT_SECRET_KEY and ENCRYPTION_KEY:
#    openssl rand -hex 32

# 2. Generate self-signed TLS certs (nginx requires them to boot)
bash healflow-devops/scripts/generate-dev-certs.sh

# 3. Start the stack (base = production-shaped, only nginx on 80/443)
docker compose -f healflow-devops/docker-compose.yml up -d --build

#    Dev variant with DB/API/metrics ports published to the host:
# docker compose -f healflow-devops/docker-compose.yml \
#                -f healflow-devops/docker-compose.dev.yml up -d --build

# 4. Check health (self-signed cert → -k)
curl -k https://localhost/health
```

Database migrations run automatically: the one-shot `migrate` service applies
`alembic upgrade head` before backend/celery start.

### Production Deployment
1. Replace `nginx/ssl/` certs with CA-issued certificates (ACM, Let's Encrypt)
2. Set strong secrets (`JWT_SECRET_KEY`, `ENCRYPTION_KEY`, DB and Grafana passwords) via your secrets manager — never commit them
3. Deploy with the base compose file only (no dev overlay)
4. Point DNS at the host; HSTS is enabled, so TLS must be valid

## Architecture

### Services
| Service | Exposure | Description |
|---------|----------|-------------|
| Nginx | host 80/443 | Reverse proxy, TLS termination, rate limiting, security headers |
| Frontend | internal :3000 | Next.js 15 standalone server |
| Backend | internal :8000 | FastAPI REST API + WebSocket chat |
| Migrate | one-shot | Alembic migrations, gates backend startup |
| Celery Worker | internal | Async task processing (message embedding) |
| Celery Beat | internal | Scheduled task trigger |
| PostgreSQL | internal :5432 | Primary database with pgvector |
| Redis | internal :6379 | Caching and Celery broker |
| Prometheus | internal :9090 | Metrics collection |
| Grafana | internal :3001 | Dashboards (publish via dev overlay) |
| OpenTelemetry | internal :4317/4318 | Distributed tracing collector |

Internal services are only published to the host when the dev overlay
(`docker-compose.dev.yml`) is added.

### Key Features
- Multi-stage Docker builds for minimal image sizes
- Health checks on all long-running services
- Automatic DB migrations via one-shot `migrate` service
- Rate limiting at Nginx level (per-IP and per-route)
- Comprehensive security headers incl. CSP and HSTS
- Prometheus + Grafana monitoring with pre-built dashboards
- OpenTelemetry for distributed tracing
- Celery for async task processing with Redis broker
- pgvector for AI-powered similarity searches
- HIPAA-compliant architecture documentation
- Non-root user execution in all containers

## CI/CD Pipelines

Workflows live in `.github/workflows/` (GitHub Actions only discovers them there).

### Backend Pipeline (`backend-ci.yml`)
1. Ruff linting (failing = red build)
2. Mypy type checking
3. Pytest with PostgreSQL + Redis service containers
4. Docker build → Trivy vulnerability scan (CRITICAL/HIGH gate) → push

### Frontend Pipeline (`frontend-ci.yml`)
1. ESLint
2. TypeScript type checking
3. Next.js production build
4. Docker build → Trivy scan → push

### Infrastructure Pipeline (`infrastructure-ci.yml`)
1. Terraform fmt/validate/plan (on PRs to main)
2. Terraform apply (on push to main, `production` environment gate)

Required repository secrets: `DOCKER_USERNAME`, `DOCKER_PASSWORD`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.

## Monitoring

### Prometheus Alert Rules
- High API latency (P95 > 2s)
- Critical API latency (P99 > 5s)
- Error rate > 5% (warning) / 10% (critical)
- Queue backlog > 1000 (warning) / 5000 (critical)
- Service down detection
- High memory usage (> 1GB)

### Grafana Dashboards
- System Health: API request rate, latency, error rate, queue depth, memory/CPU
- Message Throughput: Channel-wise message volume, delivery rates, webhook processing

## Security
- All external communication encrypted with TLS (1.2/1.3)
- Security headers enforced at Nginx level (CSP, HSTS, COOP/COEP, etc.)
- Rate limiting per IP and route
- Trivy image scanning gates every image push
- HIPAA compliance documentation in `security/`
- Secrets via environment variables — never hardcoded or committed
- Non-root user execution in all containers
