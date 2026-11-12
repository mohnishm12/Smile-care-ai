#!/bin/bash
# =============================================================================
# HealFlow AI — Create a staff/doctor/admin login
# Registers the account through the API, then promotes its role directly in
# the database (role changes are deliberately NOT exposed over the API).
#
# Usage:
#   bash create-staff-user.sh <email> <password> "<full name>" [role]
#   role: staff (default) | doctor | clinic_admin | admin
#
# Requires the compose stack to be running (backend + postgres containers).
# =============================================================================

set -euo pipefail

EMAIL="${1:?usage: create-staff-user.sh <email> <password> \"<full name>\" [role]}"
PASSWORD="${2:?password required}"
FULL_NAME="${3:?full name required}"
ROLE="${4:-staff}"

case "$ROLE" in
    staff|doctor|clinic_admin|admin) ;;
    *) echo "Invalid role '$ROLE' (use staff|doctor|clinic_admin|admin)" >&2; exit 1 ;;
esac

BASE_URL="${HEALFLOW_URL:-https://localhost}"

echo "Registering $EMAIL via $BASE_URL ..."
status=$(curl -sk -o /tmp/hf-register.json -w "%{http_code}" \
    -X POST "$BASE_URL/api/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"full_name\":\"$FULL_NAME\"}")

if [ "$status" = "201" ]; then
    echo "Account created."
elif grep -q "already registered" /tmp/hf-register.json 2>/dev/null; then
    echo "Account already exists — promoting role only."
else
    echo "Registration failed (HTTP $status):" >&2
    cat /tmp/hf-register.json >&2
    exit 1
fi

echo "Promoting $EMAIL to role '$ROLE' ..."
docker exec healflow-postgres psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-healflow}" \
    -v ON_ERROR_STOP=1 \
    -c "UPDATE healflow.users SET role = '$ROLE' WHERE email = '$EMAIL';" | grep -q "UPDATE 1" \
    || { echo "Role update failed — is the stack running and the email correct?" >&2; exit 1; }

echo "Done. $EMAIL can now sign in at $BASE_URL/dashboard/reception (role: $ROLE)."
