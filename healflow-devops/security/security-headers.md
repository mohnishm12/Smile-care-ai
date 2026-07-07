# HealFlow AI — Security Headers Configuration

## Overview
Security headers protect against common web vulnerabilities. These are configured at the Nginx reverse proxy level.

## Headers Applied

| Header | Value | Purpose |
|--------|-------|---------|
| `X-Content-Type-Options` | `nosniff` | Prevents MIME type sniffing |
| `X-Frame-Options` | `DENY` | Prevents clickjacking |
| `X-XSS-Protection` | `1; mode=block` | Enables XSS filter in older browsers |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Controls referrer information |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | Restricts browser features |
| `Cross-Origin-Embedder-Policy` | `require-corp` | Prevents cross-origin loading of resources |
| `Cross-Origin-Opener-Policy` | `same-origin` | Isolates cross-origin windows |
| `Cross-Origin-Resource-Policy` | `same-origin` | Restricts cross-origin resource reads |
| `Content-Security-Policy` | See below | Comprehensive CSP policy |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` | Enforces HTTPS |

## Content Security Policy (CSP)
```
default-src 'self';
script-src 'self' 'unsafe-inline' 'unsafe-eval';
style-src 'self' 'unsafe-inline';
img-src 'self' data: https://images.unsplash.com;
font-src 'self' data:;
connect-src 'self' https://api.healflow.ai wss://api.healflow.ai;
frame-ancestors 'none';
form-action 'self';
base-uri 'self';
```

## Implementation
Headers are set in the Nginx configuration:
- `healflow-devops/nginx/nginx.conf` — global headers
- `healflow-devops/nginx/default.conf` — per-location overrides

## Testing
Use these tools to verify security headers:
- securityheaders.com
- observatory.mozilla.org
- SSL Labs SSL Server Test

## Monitoring
- Alert on missing/incorrect headers via Prometheus
- Log header validation failures in Sentry