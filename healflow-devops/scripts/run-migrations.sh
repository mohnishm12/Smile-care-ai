#!/bin/bash
# =============================================================================
# HealFlow AI — Database Migration Runner
# Runs Alembic migrations on the target database.
# Used by the one-shot `migrate` service in docker-compose.yml; connection
# comes from DATABASE_URL / DATABASE_SYNC_URL, same env as the app itself.
# =============================================================================

set -euo pipefail

echo "=== HealFlow AI Database Migration ==="
echo "Environment: ${ENVIRONMENT:-development}"

cd /app

# Wait for the database to accept connections (no pg_isready in the slim
# image — probe with the same driver stack alembic will use).
echo "Waiting for database..."
for attempt in $(seq 1 30); do
    if python - <<'EOF'
import sys
from sqlalchemy import create_engine, text
from src.config import get_settings

try:
    engine = create_engine(get_settings().database_sync_url, connect_args={"connect_timeout": 3})
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
except Exception:
    sys.exit(1)
EOF
    then
        echo "Database is ready."
        break
    fi
    if [ "$attempt" -eq 30 ]; then
        echo "Database not reachable after 30 attempts — giving up." >&2
        exit 1
    fi
    sleep 2
done

echo "Running Alembic migrations..."
alembic upgrade head

echo "Migrations complete."
