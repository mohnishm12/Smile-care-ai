# HealFlow AI — DevOps Infrastructure

## Overview
This directory contains all infrastructure, deployment, and monitoring configurations for HealFlow AI — an enterprise-grade omnichannel patient communication platform.

## Directory Structure

```
healflow-devops/
├── .env.example              # Environment variable template
├── README.md                 # This file
├── docker-compose.yml        # Main orchestration file
├── docker/                   # Dockerfiles for all services
│   ├── Dockerfile.backend    # FastAPI backend (multi-stage)
│   ├── Dockerfile.frontend   # Next.js frontend (with Nginx)
│   ├── Dockerfile.celery     # Celery worker/beat
│   ├── backend.dockerignore
│   └── frontend.dockerignore
├── ci-cd/                    # GitHub Actions pipelines
│   ├── backend-ci.yml        # Backend lint, test, build, push
│   ├── frontend-ci.yml       # Frontend lint, type-check, build, push
│   └── infrastructure-ci.yml # Terraform plan/apply
├── nginx/                    # Reverse proxy configuration
│   ├── nginx.conf            # Main nginx config with security headers
│   ├── default.conf          # Virtual host config
│   └── ssl/                  # SSL certificates (add your certs here)
├── monitoring/               # Observability stack
│   ├── prometheus/
│   │   ├── prometheus.yml    # Scrape configs
│   │   └── alert.rules.yml   # Alerting rules
│   ├── grafana/
│   │   ├── datasources/      # Prometheus datasource
│   │   └── dashboards/       # Pre-built dashboards
│   └── otel/
│       └── otel-collector-config.yml  # OpenTelemetry collector
├── security/                 # Security and compliance documentation
│   ├── HIPAA_COMPLIANCE.md   # HIPAA compliance architecture guide
│   └── security-headers.md   # Security headers configuration
└── scripts/                  # Utility scripts
    ├── init-db.sql           # Database initialization
    ├── run-migrations.sh     # Alembic migration runner
    └── healthcheck-backend.sh # Backend health check
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

# Copy environment configuration
cp healflow-devops/.env.example .env
# Edit .env with your settings

# Start all services
docker compose -f healflow-devops/docker-compose.yml up -d

# Check health
curl http://localhost:8000/health
```

### Production Deployment
1. Set up SSL certificates in `nginx/ssl/`
2. Configure environment variables in your CI/CD or secrets manager
3. Deploy using Docker Compose or Kubernetes manifests (coming soon)

## Architecture

### Services
| Service | Port | Description |
|---------|------|-------------|
| Nginx | 80/443 | Reverse proxy, SSL termination, rate limiting |
| Frontend | 3000 | Next.js 15 web application |
| Backend | 8000 | FastAPI REST API |
| Celery Worker | - | Async task processing |
| Celery Beat | - | Scheduled task trigger |
| PostgreSQL | 5432 | Primary database with pgvector |
| Redis | 6379 | Caching and message broker |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3001 | Visualization dashboards |
| OpenTelemetry | 4317/4318 | Distributed tracing |

### Key Features
- Multi-stage Docker builds for minimal image sizes
- Health checks on all services
- Rate limiting at Nginx level (per-IP and per-route)
- Comprehensive security headers
- Prometheus + Grafana monitoring with pre-built dashboards
- OpenTelemetry for distributed tracing
- Celery for async task processing with Redis broker
- pgvector for AI-powered similarity searches
- HIPAA-compliant architecture documentation

## CI/CD Pipelines

### Backend Pipeline
1. Ruff linting
2. Mypy type checking
3. Pytest with PostgreSQL + Redis service containers
4. Docker build and push (on push to develop/main)

### Frontend Pipeline
1. ESLint
2. TypeScript type checking
3. Next.js production build
4. Docker build and push (on push to develop/main)

### Infrastructure Pipeline
1. Terraform plan (on PRs to main)
2. Terraform apply (on push to main)
3. AWS infrastructure deployment

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
- All external communication encrypted with TLS 1.3
- Security headers enforced at Nginx level
- Rate limiting per IP and route
- HIPAA compliance documentation included
- Secrets management via environment variables (never hardcoded)
- Non-root user execution in all containers