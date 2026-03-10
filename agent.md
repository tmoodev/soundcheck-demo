# SoundCheck Financial -- Agent Operations Manual

> This document contains everything needed to manage the SoundCheck Financial production instance.
> Load this file at the start of every session.

---

## Instance Identity

| Field | Value |
|-------|-------|
| **Application** | SoundCheck Financial -- Multi-tenant financial dashboard |
| **Provider** | AWS (us-east-1) |
| **EC2 Instance ID** | `i-088b06e8cf95fc3f4` |
| **EC2 Public IP** | `100.54.26.231` |
| **EC2 Public DNS** | `ec2-100-54-26-231.compute-1.amazonaws.com` |
| **OS** | Ubuntu 22.04 LTS |
| **Instance Type** | t3.small (2 vCPU, 2 GB RAM) |
| **Disk** | 20 GB gp3 |

**SSH access:**
```bash
ssh -i ~/.ssh/soundcheck-ec2.pem ubuntu@100.54.26.231
```
Key file: `~/.ssh/soundcheck-ec2.pem` (AWS key pair: `soundcheck-ec2`)
SSH restricted to `136.58.18.216/32` (office egress IP).

---

## Users and Access

| User | Purpose | Sudo |
|------|---------|------|
| `ubuntu` | Default AWS user, SSH entry point | Yes (passwordless) |
| `soundcheck` | Application service account, owns the codebase | No |

**Run commands as soundcheck:**
```bash
sudo -u soundcheck bash -c 'cd /home/soundcheck/soundcheck_v2 && source venv/bin/activate && <command>'
```

---

## Application Stack

| Component | Version | Details |
|-----------|---------|---------|
| **Python** | 3.11 | Virtualenv at `/home/soundcheck/soundcheck_v2/venv/` |
| **Django** | 4.2.28 | Multi-tenant via `django-tenants` 3.10.0 (schema-per-tenant) |
| **Gunicorn** | 25.0.3 | 4 workers, bound to `127.0.0.1:8000` |
| **PostgreSQL** | 15.10 (RDS) | See Database section below |
| **Plaid** | plaid-python 38.1.0 | **Production** environment |
| **Cloudflared** | 2026.3.0 | Tunnel ID: `09b1ed58-4dee-42a7-93f8-778a95a20158` |

---

## Database (RDS)

| Field | Value |
|-------|-------|
| **Engine** | PostgreSQL 15.10 |
| **Instance** | `soundcheck-db` (db.t3.micro) |
| **Endpoint** | `soundcheck-db.cetwoug00f0j.us-east-1.rds.amazonaws.com` |
| **Port** | `5432` |
| **Database** | `soundcheck` |
| **User** | `soundcheck` |
| **Security Group** | `sg-065f6ba151567c026` (soundcheck-rds) — port 5432 from EC2 SG only |

Connect from EC2:
```bash
PGPASSWORD=<password> psql -h soundcheck-db.cetwoug00f0j.us-east-1.rds.amazonaws.com -U soundcheck -d soundcheck
```

---

## AWS Resources

| Resource | ID / Value |
|----------|-----------|
| **VPC** | `vpc-057d2aa51e7c7b762` (default, us-east-1) |
| **Subnet** | `subnet-000101a217ce795ca` (us-east-1a, public) |
| **EC2 Security Group** | `sg-0d1e06a45f1f0b9d4` (soundcheck-ec2) |
| **RDS Security Group** | `sg-065f6ba151567c026` (soundcheck-rds) |

---

## File Paths

| What | Path |
|------|------|
| **Project root** | `/home/soundcheck/soundcheck_v2/` |
| **Virtualenv** | `/home/soundcheck/soundcheck_v2/venv/` |
| **Django manage.py** | `/home/soundcheck/soundcheck_v2/manage.py` |
| **Settings** | `/home/soundcheck/soundcheck_v2/soundcheck/settings.py` |
| **Environment vars** | `/home/soundcheck/soundcheck_v2/.env` |
| **Templates** | `/home/soundcheck/soundcheck_v2/templates/` |
| **Static files** | `/home/soundcheck/soundcheck_v2/static/` (source), `staticfiles/` (collected) |
| **Gunicorn service** | `/etc/systemd/system/soundcheck.service` |
| **Cloudflared service** | `/etc/systemd/system/cloudflared.service` |
| **Cloudflared config** | `/etc/cloudflared/config.yml` |
| **Cloudflared creds** | `/etc/cloudflared/09b1ed58-4dee-42a7-93f8-778a95a20158.json` |
| **Cloudflared auth cert** | `/root/.cloudflared/cert.pem` (used for `tunnel route dns` commands) |

---

## Django Apps

| App | Type | Purpose |
|-----|------|---------|
| `tenants` | Shared | Tenant and Domain models, `WebhookItemTenantMap` for webhook routing |
| `accounts` | Shared + Tenant | Custom User model with MFA (TOTP), `TrustedDevice`, `PasswordResetToken` |
| `clients` | Tenant | Client and ClientAccount models (maps clients to Plaid account_ids) |
| `dashboard` | Tenant | Summary/Transactions views, queries, CSV export, admin panel views |
| `auditlog` | Tenant | AuditEntry model for security event logging |
| `plaid_ingest` | Tenant | Plaid integration: items, accounts, balances, transactions, sync, webhooks |

### URL Structure

**Tenant URLs** (`soundcheck/urls.py`):
- `/` -- redirects to `/dashboard/`
- `/auth/` -- login, logout, MFA setup/verify, password reset
- `/dashboard/` -- summary, transactions, CSV export
- `/manage/` -- admin panel (users, clients, banks, audit)
- `/api/plaid/` -- Plaid API endpoints (link-token, exchange-token, items, sync, refresh)
- `/django-admin/` -- Django admin

**Public Schema URLs** (`soundcheck/urls_public.py`):
- `/` -- landing page
- `/api/plaid/webhook/` -- Plaid webhook receiver (unauthenticated)

---

## Tenants

| Schema | Name | Domain | Admin Email |
|--------|------|--------|-------------|
| `public` | Public | `api.soundcheckfinancial.com` | — (webhook only) |
| `demo` | Demo | `demo.soundcheckfinancial.com` | `admin@demo.local` |
| `moore` | Moore | `moore.soundcheckfinancial.com` | `travis@digitalmoore.com` |
| `clineco` | Cline-Co | `clineco.soundcheckfinancial.com` | `admin@cline-co.com` |

Initial admin password for all tenants: `TempPass123!` — change on first login.

---

## Database Schemas

| Schema | Purpose |
|--------|---------|
| `public` | Shared Django tables, tenant registry, `webhook_item_tenant_map` |
| `demo` | Demo tenant data |
| `moore` | Moore tenant data |
| `clineco` | Cline-Co tenant data |

---

## Plaid Integration

| Setting | Value |
|---------|-------|
| **Client ID** | `69691f393734c100217b330e` |
| **Environment** | `production` |
| **Webhook URL** | `https://api.soundcheckfinancial.com/api/plaid/webhook/` |

### Plaid Ingest Models (tenant-scoped)

- `PlaidItem` -- bank connection (item_id, encrypted access_token, institution, client FK, status)
- `PlaidAccount` -- financial account within an item
- `PlaidAccountBalance` -- current balance snapshot (1:1 with account)
- `PlaidTransaction` -- individual transactions
- `PlaidSyncCursor` -- tracks cursor for `/transactions/sync` (1:1 with item)
- `PlaidWebhookEvent` -- webhook audit log with dedup

### Access Token Encryption

Access tokens are encrypted at rest using Fernet symmetric encryption (in `plaid_ingest/encryption.py`). The key is derived from `DJANGO_SECRET_KEY` via SHA-256. **If the secret key changes, all stored access tokens become unreadable.**

### Webhook Routing

Plaid sends webhooks to `https://api.soundcheckfinancial.com/api/plaid/webhook/` (public schema). The handler:
1. Extracts `item_id` from the payload
2. Looks up the tenant via `public.webhook_item_tenant_map`
3. Switches to the correct tenant schema via `schema_context()`
4. Dispatches the event (sync transactions, update item status, etc.)

---

## Cloudflare Tunnel

| Field | Value |
|-------|-------|
| **Tunnel ID** | `09b1ed58-4dee-42a7-93f8-778a95a20158` |
| **Config** | `/etc/cloudflared/config.yml` |
| **Credentials** | `/etc/cloudflared/09b1ed58-4dee-42a7-93f8-778a95a20158.json` |
| **Auth cert** | `/root/.cloudflared/cert.pem` (required for `tunnel route dns` commands) |

### Ingress Rules

| Hostname | Backend |
|----------|---------|
| `demo.soundcheckfinancial.com` | `http://127.0.0.1:8000` |
| `moore.soundcheckfinancial.com` | `http://127.0.0.1:8000` |
| `api.soundcheckfinancial.com` | `http://127.0.0.1:8000` |
| `clineco.soundcheckfinancial.com` | `http://127.0.0.1:8000` |
| Catch-all | `http_status:404` |

### Adding a New Tenant Subdomain

1. Provision the tenant:
   ```bash
   python manage.py provision_tenant --name "..." --slug <slug> \
     --domain <slug>.soundcheckfinancial.com --admin-email ...
   ```
2. Add ingress rule to `/etc/cloudflared/config.yml` (before the catch-all):
   ```yaml
   - hostname: <slug>.soundcheckfinancial.com
     service: http://127.0.0.1:8000
     originRequest:
       httpHostHeader: <slug>.soundcheckfinancial.com
   ```
3. Add DNS CNAME via cloudflared (requires cert at `/root/.cloudflared/cert.pem`):
   ```bash
   sudo cloudflared tunnel route dns 09b1ed58-4dee-42a7-93f8-778a95a20158 <slug>.soundcheckfinancial.com
   ```
4. Restart services:
   ```bash
   sudo systemctl restart cloudflared && sudo systemctl restart soundcheck
   ```

---

## Service Management

### Restart application
```bash
sudo systemctl restart soundcheck
```

### Restart tunnel
```bash
sudo systemctl restart cloudflared
```

### Check status
```bash
sudo systemctl status soundcheck --no-pager
sudo systemctl status cloudflared --no-pager
```

### View application logs
```bash
sudo journalctl -u soundcheck -f                                          # follow live
sudo journalctl -u soundcheck --since "5 min ago" --no-pager
sudo journalctl -u soundcheck --since "5 min ago" --no-pager | grep -i error
```

### View tunnel logs
```bash
sudo journalctl -u cloudflared -f
```

### Django shell
```bash
cd /home/soundcheck/soundcheck_v2 && source venv/bin/activate
python manage.py shell
```

### Django shell with tenant context
```python
from django_tenants.utils import schema_context
with schema_context('demo'):
    from plaid_ingest.models import PlaidItem
    print(PlaidItem.objects.count())
```

---

## Management Commands

### Provision a new tenant
```bash
python manage.py provision_tenant \
    --name "Tenant Name" \
    --slug tenantslug \
    --domain tenantslug.soundcheckfinancial.com \
    --admin-email admin@example.com \
    --admin-password "SecurePassword10+"
```

### Sync all Plaid items (all tenants)
```bash
python manage.py sync_all_items                    # all tenants
python manage.py sync_all_items --tenant demo      # specific tenant
python manage.py sync_all_items --balances         # also refresh balances
```

### Run migrations
```bash
python manage.py makemigrations
python manage.py migrate_schemas --shared    # shared/public schema
python manage.py migrate_schemas --tenant    # all tenant schemas
```

### Collect static files
```bash
python manage.py collectstatic --noinput
```

---

## MFA Operations

### Reset MFA for a user (Django shell)
```python
from django_tenants.utils import schema_context
with schema_context('demo'):  # replace with target tenant
    from accounts.models import User, TrustedDevice
    user = User.objects.get(email='admin@demo.local')
    user.mfa_secret = ''
    user.mfa_enabled = False
    user.mfa_confirmed = False
    user.recovery_codes = []
    user.save()
    TrustedDevice.objects.filter(user=user).delete()
```

### Or via the admin panel
Navigate to Manage > Users > click the user > Reset MFA button.

---

## Email Configuration

| Setting | Value |
|---------|-------|
| **SMTP Host** | `smtp.office365.com` |
| **Port** | 587 (STARTTLS) |
| **User** | `noreply@soundcheckfinancial.com` |
| **From** | `noreply@soundcheckfinancial.com` |

Used for password reset emails.

---

## Known Issues and Notes

1. **No cron jobs**: `sync_all_items` is not yet scheduled. To add:
   ```
   # Example: sync every 6 hours
   0 */6 * * * /home/soundcheck/soundcheck_v2/venv/bin/python /home/soundcheck/soundcheck_v2/manage.py sync_all_items --balances >> /var/log/soundcheck-sync.log 2>&1
   ```

2. **Plaid webhook signature verification**: Not yet implemented. The webhook endpoint accepts any POST. Implement JWT signature verification using Plaid's `/webhook_verification_key/get` endpoint before trusting webhook payloads.

3. **SECURE_SSL_REDIRECT**: Set to `False` in `.env`. Cloudflare handles HTTPS enforcement at the edge.

4. **RDS deletion protection**: Enabled. Must be disabled in AWS console before the instance can be deleted.

---

## Quick Troubleshooting

### Dashboard shows 500
1. Check logs: `sudo journalctl -u soundcheck --since "2 min ago" --no-pager`
2. Common causes: missing migrations, missing tenant data, Plaid API errors

### Site unreachable
1. Check gunicorn: `sudo systemctl status soundcheck`
2. Check tunnel: `sudo systemctl status cloudflared`
3. Check DNS: `dig demo.soundcheckfinancial.com`

### Plaid sync errors
1. Check item status in Django shell
2. Check webhook events: `PlaidWebhookEvent.objects.order_by('-received_at')[:10]`
3. Manual sync: `python manage.py sync_all_items --tenant <slug>`

### New tenant not accessible
1. Verify domain record: `Domain.objects.all()` in Django shell
2. Verify cloudflared ingress rule includes the hostname in `/etc/cloudflared/config.yml`
3. Verify DNS CNAME: `sudo cloudflared tunnel route dns 09b1ed58-4dee-42a7-93f8-778a95a20158 <hostname>`
4. Restart both services

---

*Last updated: 2026-03-10*
