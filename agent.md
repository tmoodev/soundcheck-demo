# SoundCheck Financial -- Agent Operations Manual

> This document contains everything needed to manage the SoundCheck Financial production instance.
> Load this file at the start of every session.

---

## Instance Identity

| Field | Value |
|-------|-------|
| **Application** | SoundCheck Financial -- Multi-tenant financial dashboard |
| **Hostname** | `app-soundcheck` |
| **Public IP** | `136.58.18.216` |
| **OS** | Ubuntu 22.04.5 LTS (Jammy), kernel 5.15.0-170-generic, x86_64 |
| **RAM** | 15 GiB |
| **Disk** | 24G root (`/dev/mapper/ubuntu--vg-ubuntu--lv`) |

---

## Users and Access

| User | UID | Purpose | Sudo |
|------|-----|---------|------|
| `travis` | 1000 | Agent operator, member of `soundcheck` group | Yes (password: `Theo@4309`) |
| `soundcheck` | 1001 | Application service account, owns the codebase | Yes (password required) |

**Sudo pattern** (travis has password-based sudo):
```bash
export SUDO_ASKPASS=/tmp/askpass.sh
printf '#!/bin/sh\necho "Theo@4309"\n' > /tmp/askpass.sh
chmod 700 /tmp/askpass.sh
sudo -A <command>
rm -f /tmp/askpass.sh
```

---

## Application Stack

| Component | Version | Details |
|-----------|---------|---------|
| **Python** | 3.11.0rc1 | Virtualenv at `/home/soundcheck/soundcheck_v2/venv/` |
| **Django** | 4.2.28 | Multi-tenant via `django-tenants` 3.10.0 (schema-per-tenant) |
| **Gunicorn** | 25.0.3 | 4 workers, bound to `127.0.0.1:8000` |
| **PostgreSQL** | Remote | Host `10.139.0.201:5432`, database `clineco`, user `clineco` |
| **Plaid** | plaid-python 38.1.0 | Sandbox environment |
| **Cloudflared** | Latest | Tunnel `soundcheck-demo` (ID: `09b1ed58-4dee-42a7-93f8-778a95a20158`) |
| **Nginx** | Installed but DISABLED | Not in use; all traffic routes through cloudflared tunnel |

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
| **Nginx config** | `/home/soundcheck/soundcheck_v2/deploy/nginx.conf` (reference only, nginx disabled) |
| **SSL certs** | `/etc/nginx/ssl/cloudflare-origin.pem`, `/etc/nginx/ssl/cloudflare-origin.key` |

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

| Schema | Name | Domains |
|--------|------|---------|
| `public` | Public | `api.soundcheckfinancial.com` (webhook endpoint) |
| `demo` | Demo Organization | `demo.soundcheckfinancial.com`, `demo.soundcheck.local`, `demo.localhost` |
| `moore` | Moore Family | `moore.soundcheckfinancial.com` |

### Tenant Admin Users

| Tenant | Email | Role |
|--------|-------|------|
| demo | `admin@demo.local` | admin |
| moore | `travis@digitalmoore.com` | admin |

---

## Database Schemas

| Schema | Purpose |
|--------|---------|
| `public` | Shared Django tables, tenant registry, `webhook_item_tenant_map` |
| `demo` | Demo tenant data (users, clients, plaid_item/account/transaction, etc.) |
| `moore` | Moore tenant data (same structure) |
| `plaid` | **LEGACY** -- Original shared Plaid data. Demo data has been migrated to tenant-scoped `plaid_ingest` models. Can be dropped after verification. |
| `analytics` | **LEGACY** -- Views (`vw_superset_accounts_current`, `vw_superset_transactions`) that query `plaid.*`. No longer used by the app (dashboard now queries ORM models). |

---

## Plaid Integration

| Setting | Value |
|---------|-------|
| **Client ID** | `69691f393734c100217b330e` |
| **Secret** | `b0f05746f2e77644aef90fe9f7a1e1` |
| **Environment** | `sandbox` |
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
| **Tunnel name** | `soundcheck-demo` |
| **Tunnel ID** | `09b1ed58-4dee-42a7-93f8-778a95a20158` |
| **Config** | `/etc/cloudflared/config.yml` |
| **Credentials** | `/etc/cloudflared/09b1ed58-4dee-42a7-93f8-778a95a20158.json` |
| **Auth cert** | `/home/travis/.cloudflared/cert.pem` (for CLI commands like `tunnel route dns`) |

### Ingress Rules

| Hostname | Backend |
|----------|---------|
| `demo.soundcheckfinancial.com` | `http://127.0.0.1:8000` |
| `moore.soundcheckfinancial.com` | `http://127.0.0.1:8000` |
| `api.soundcheckfinancial.com` | `http://127.0.0.1:8000` |
| Catch-all | `http_status:404` |

### Adding a New Tenant Subdomain

1. Provision the tenant: `python manage.py provision_tenant --name "..." --slug <slug> --domain <slug>.soundcheckfinancial.com --admin-email ... --admin-first-name ... --admin-last-name ...`
2. Add CSRF origin to `.env`: append `https://<slug>.soundcheckfinancial.com` to `CSRF_TRUSTED_ORIGINS`
3. Add ingress rule to `/etc/cloudflared/config.yml` (before the catch-all)
4. Create DNS route: `cloudflared tunnel route dns soundcheck-demo <slug>.soundcheckfinancial.com`
5. Restart services: `sudo systemctl restart cloudflared && sudo systemctl restart soundcheck`

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
sudo journalctl -u soundcheck -f              # follow live
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
    --admin-first-name "First" \
    --admin-last-name "Last" \
    --admin-password "SecurePassword10+"
```

### Sync all Plaid items (all tenants)
```bash
python manage.py sync_all_items                    # all tenants
python manage.py sync_all_items --tenant demo      # specific tenant
python manage.py sync_all_items --balances         # also refresh balances
```

### Migrate legacy Plaid data into a tenant
```bash
python manage.py migrate_plaid_data --tenant demo --client-name "Client Name"
python manage.py migrate_plaid_data --tenant demo --dry-run   # preview only
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
with schema_context('demo'):  # or 'moore'
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
| **Password** | `vczstckklrskrjvd` |
| **From** | `noreply@soundcheckfinancial.com` |

Used for password reset emails.

---

## Known Issues and Notes

1. **File ownership mismatch**: The `plaid_ingest/` directory is owned by `travis:travis` while the rest of the codebase is `soundcheck:soundcheck`. This works because `travis` is in the `soundcheck` group and directories have group write permissions. To normalize: `sudo chown -R soundcheck:soundcheck /home/soundcheck/soundcheck_v2/plaid_ingest/`

2. **Legacy schemas**: The `plaid` and `analytics` schemas are legacy. The demo tenant data has been migrated to tenant-scoped `plaid_ingest` models. The `analytics` views are no longer queried by the dashboard. These schemas can be dropped after confirming everything works.

3. **CSRF_TRUSTED_ORIGINS duplication**: The `.env` file has `CSRF_TRUSTED_ORIGINS` defined twice (lines 4 and near the bottom under Security). The second one wins. When adding new tenant origins, update the **second** occurrence.

4. **No cron jobs**: `sync_all_items` is not yet scheduled via cron. To add:
   ```
   # Example: sync every 6 hours
   0 */6 * * * /home/soundcheck/soundcheck_v2/venv/bin/python /home/soundcheck/soundcheck_v2/manage.py sync_all_items --balances >> /var/log/soundcheck-sync.log 2>&1
   ```

5. **Plaid webhook signature verification**: Not yet implemented. The webhook endpoint accepts any POST. Before going to production, implement JWT signature verification using Plaid's `/webhook_verification_key/get` endpoint.

6. **DJANGO_SECRET_KEY**: Currently set to `THISISJUSTATEST123`. This **must** be changed to a secure random value before production. Generate with: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`. **Warning**: Changing the secret key will invalidate all sessions and encrypted Plaid access tokens.

7. **SECURE_SSL_REDIRECT**: Set to `False` in `.env` to allow local HTTP access. Cloudflare handles HTTPS enforcement at the edge.

8. **Git**: The repo at `/home/soundcheck/soundcheck_v2/.git` refuses operations as `travis` due to ownership. Run `git config --global --add safe.directory /home/soundcheck/soundcheck_v2` to fix.

---

## Dependency List (pip freeze)

```
argon2-cffi==25.1.0
argon2-cffi-bindings==25.1.0
asgiref==3.11.1
cffi==2.0.0
cryptography==46.0.5
Django==4.2.28
django-otp==1.7.0
django-ratelimit==4.1.0
django-tenants==3.10.0
djangorestframework==3.16.1
gunicorn==25.0.3
nulltype==2.3.1
packaging==26.0
pillow==12.1.1
plaid-python==38.1.0
psycopg2-binary==2.9.11
pycparser==3.0
pyotp==2.9.0
python-dateutil==2.9.0.post0
python-dotenv==1.2.1
qrcode==8.2
six==1.17.0
sqlparse==0.5.5
urllib3==2.6.3
whitenoise==6.11.0
```

---

## Quick Troubleshooting

### Dashboard shows 500
1. Check logs: `sudo journalctl -u soundcheck --since "2 min ago" --no-pager`
2. Common cause: database column name mismatches, missing migrations, or missing tenant data

### Site unreachable
1. Check gunicorn: `sudo systemctl status soundcheck`
2. Check tunnel: `sudo systemctl status cloudflared`
3. Check DNS: `dig demo.soundcheckfinancial.com`

### Plaid sync errors
1. Check item status in Django shell
2. Check webhook events: query `PlaidWebhookEvent.objects.order_by('-received_at')[:10]`
3. Manual sync: `python manage.py sync_all_items --tenant <slug>`

### New tenant not accessible
1. Verify domain record exists: check `Domain.objects.all()` in Django shell
2. Verify cloudflared ingress rule includes the hostname
3. Verify DNS CNAME created: `cloudflared tunnel route dns soundcheck-demo <hostname>`
4. Verify CSRF origin added to `.env`
5. Restart both services

---

*Last updated: 2026-02-13*
