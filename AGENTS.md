# soundcheck-demo

> Scaffolded 2026-11-23 by the KB sleep cycle (`scripts/sleep/agents_scaffold.py`) from the knowledge base, the repo's manifests and its previous CLAUDE.md. Sections are only as good as those sources; correct State and Gotchas on first real use and the next `/kb-update` makes it yours.

## Overview

SoundCheck Financial is a secure, multi-tenant Django dashboard replacing an existing Superset analytics interface. It serves financial institutions and their end-users, providing isolated data views per tenant via PostgreSQL schema-per-tenant architecture (`django-tenants`). The system delivers account summaries, transaction filtering, and CSV export capabilities while enforcing mandatory multi-factor authentication (MFA) via TOTP (RFC 6238). Each tenant operates within its own PostgreSQL schema, ensuring complete data isolation, and accesses the application through subdomains routed via Cloudflare. The platform is designed for regulatory compliance in financial services, featuring an immutable audit trail, rate-limited endpoints, and strict tenant separation.

## Stack

- **Backend**: Django 4.2 (from `requirements.txt`)
- **Multi-tenancy**: django-tenants 3.6
- **MFA**: pyotp 2.9, django-otp 1.3
- **Frontend**: HTMX + Tailwind CSS (CDN)
- **Database**: PostgreSQL (existing analytics views)
- **Deployment**: Ubuntu + systemd + nginx + Cloudflare
- **Dependencies**: gunicorn 21.2, psycopg2-binary 2.9, whitenoise 6.5
- **Security**: argon2-cffi 23.1, django-ratelimit 4.1, cryptography 42.0

## Architecture

- **Reverse Proxy**: Cloudflare terminates TLS and proxies requests to nginx on the origin server.
- **Web Server**: nginx routes traffic to gunicorn (Django WSGI server) via Unix socket.
- **Application**: Django 4.2 with django-tenants handles schema routing; each tenant has isolated PostgreSQL schema.
- **Data Flow**:
  - Public schema serves landing page.
  - Tenant subdomains (e.g., `acme.soundcheckfinancial.com`) route to tenant-specific schemas.
  - Django middleware enforces MFA and tenant isolation.
  - Dashboard reads from existing analytics views (`analytics.vw_superset_accounts_current`, `analytics.vw_superset_transactions`) and new application tables (`app_client`, `audit_log`).
- **Infrastructure**: Runs on a single Ubuntu server (not containerized), with systemd managing gunicorn and nginx.

## Deploy

- **Method**: Manual deployment via SSH to origin server (noted as `NOT_ON_EC2` in deploy config).
- **Server**: Ubuntu 22.04+ (as documented in README).
- **Path**: `/home/soundcheck/soundcheck_v2`.
- **Services**: gunicorn (Django), nginx, PostgreSQL.
- **Commands**:
  ```bash
  # Server preparation
  sudo apt update && sudo apt install -y python3.11 python3.11-venv postgresql nginx
  sudo useradd -m -s /bin/bash soundcheck
  sudo -u soundcheck bash
  
  # Application setup
  cd /home/soundcheck
  git clone <repo-url> soundcheck_v2
  cd soundcheck_v2
  python3.11 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  cp .env.example .env  # Edit with production values
  python manage.py migrate_schemas --shared
  python manage.py collectstatic --noinput
  
  # Systemd
  sudo cp deploy/soundcheck.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable soundcheck
  sudo systemctl start soundcheck
  
  # Nginx
  sudo cp deploy/nginx.conf /etc/nginx/sites-available/soundcheck
  sudo ln -s /etc/nginx/sites-available/soundcheck /etc/nginx/sites-enabled/
  sudo rm -f /etc/nginx/sites-enabled/default
  sudo nginx -t && sudo systemctl reload nginx
  ```
- **Rule**: Manual deployment as documented (no GitHub Actions).

## Environments / URLs

| Environment | URL | Host | Port | Notes |
|-------------|-----|------|------|-------|
| Demo | https://demo.soundcheckfinancial.com | Origin server (Ubuntu) | 443 (Cloudflare) | Cloudflare-proxied, TLS enforced |
| Tenant | https://`<tenant-slug>`.soundcheckfinancial.com | Origin server | 443 | Wildcard DNS (Cloudflare) |
| Local Dev | http://`<tenant-slug>`.localhost:8000 | localhost | 8000 | Requires `/etc/hosts` entry |
| Public Schema | http://`<domain>`:8000 | localhost | 8000 | Landing page only |

## State

As of 2026-11-23 (scaffolded from the KB; verify):
- **Live**: Demo environment (`demo.soundcheckfinancial.com`) as per deploy config (`status: demo`).
- **Not Running**: No evidence of staging or production environments in sources.
- **In Flight**: Tenant provisioning workflow (manual via `provision_tenant` command) is documented but not automated.
- **Pending**: Cloudflare wildcard DNS setup (requires paid plan) for dynamic tenant subdomains.

## History

- **2026-06-10**: Deploy config for `soundcheck-demo` migrated (source: human).
- **2026-06-09**: Deploy config last verified (confidence: medium).

## Gotchas

- **Tenant DNS**: Cloudflare wildcard DNS (`*.soundcheckfinancial.com`) requires a paid plan; tenants must be added manually otherwise.
- **Analytics Views**: Tenant schemas must contain `analytics.vw_superset_accounts_current` and `analytics.vw_superset_transactions` views for the dashboard to function.
- **MFA Time Sync**: TOTP verification requires server time to be synchronized (NTP); drift >30s will cause failures.
- **Schema Isolation**: `migrate_schemas --shared` must run before tenant migrations; cross-schema queries are blocked by django-tenants.
- **CSV Export**: Limited to 250,000 rows; larger exports require narrowing filters or risk timeout.
- **Rate Limits**: Login, MFA verify, and password reset endpoints are rate-limited (10 req/min, 5 req/min respectively).
- **Static Files**: `collectstatic` must run in production; whitenoise serves files via Django.
- **Environment Variables**: `CSRF_TRUSTED_ORIGINS` must include `https://*.soundcheckfinancial.com` for subdomain support.

## KB pointer

`kb/products/soundcheck-demo.md` and `deploy/soundcheck-demo.md` in `datatrav-ops-kb` (`~/code/datatrav-ops-kb` on the workstation). Read the session brief `briefings/soundcheck-demo.md` first; open the KB files when the brief cites them. After a commit, push or deploy, run `/kb-update`.

Cloud/mobile sessions: attach `tmoodev/datatrav-ops-kb` with `add_repo`, then read its `cloud/global-rules.md` and `AGENTS.md`.
