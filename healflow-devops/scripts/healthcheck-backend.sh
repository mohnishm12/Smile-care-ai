#!/bin/bash
# =============================================================================
# HealFlow AI — Backend Health Check Script
# Used by Docker HEALTHCHECK instruction
# =============================================================================

set -euo pipefail

response=$(curl -sf http://localhost:8000/health 2>/dev/null) || {
    echo "Failed to connect to backend health endpoint"
    exit 1
}

status=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null) || {
    echo "Failed to parse health response: $response"
    exit 1
}

if [ "$status" != "healthy" ]; then
    echo "Health check failed: status=$status"
    exit 1
fi

echo "Health check passed"
exit 0