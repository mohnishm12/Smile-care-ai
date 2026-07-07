#!/bin/bash
# =============================================================================
# HealFlow AI — Database Migration Runner
# Runs Alembic migrations on the target database
# =============================================================================

set -euo pipefail

echo "=== HealFlow AI Database Migration ==="
echo "Environment: ${ENVIRONMENT:-development}"
echo "Database URL: ${DATABASE_URL:-local}"

# Wait for database to be ready
echo "Waiting for database..."
until pg_isready -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" -U "${DB_USER:-postgres}" 2>/dev/null; do
    sleep 2
done
echo "Database is ready."

# Run migrations
echo "Running Alembic migrations..."
cd /app
alembic upgrade head

echo "Migrations complete."