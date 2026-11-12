#!/bin/bash
# =============================================================================
# HealFlow AI — Self-Signed Dev Certificate Generator
# Nginx refuses to start without ssl_certificate/ssl_certificate_key present.
# Run this once before `docker compose up` in local/dev environments.
# Production deployments must replace these with certs from a real CA
# (ACM, Let's Encrypt/certbot, etc.) — never ship this self-signed pair.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSL_DIR="$SCRIPT_DIR/../nginx/ssl"

mkdir -p "$SSL_DIR"

if [[ -f "$SSL_DIR/cert.pem" && -f "$SSL_DIR/key.pem" ]]; then
    echo "Dev certs already exist at $SSL_DIR — skipping."
    exit 0
fi

# Run inside the target dir with relative filenames and MSYS_NO_PATHCONV so
# the same script works on Linux, macOS, and Git Bash on Windows (whose path
# mangling otherwise corrupts the -subj argument).
cd "$SSL_DIR"
MSYS_NO_PATHCONV=1 openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout key.pem \
    -out cert.pem \
    -days 365 \
    -subj "/C=US/ST=Dev/L=Dev/O=HealFlow AI/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

chmod 644 cert.pem
chmod 600 key.pem

echo "Self-signed dev cert generated at $SSL_DIR"
echo "Browsers will warn about it — that's expected for local dev."
