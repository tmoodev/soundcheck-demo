"""
One-time migration command to move data from the shared plaid.* schema
into tenant-scoped plaid_ingest models.

Usage:
    python manage.py migrate_plaid_data --tenant demo
    python manage.py migrate_plaid_data --tenant demo --client-name "Demo Client"
"""
import logging
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from django_tenants.utils import schema_context
from tenants.models import Tenant

logger = logging.getLogger("soundcheck")


class Command(BaseCommand):
    help = "Migrate data from the shared plaid.* schema into tenant-scoped plaid_ingest models."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant slug to migrate data into")
        parser.add_argument(
            "--client-name",
            default=None,
            help="Name of the Client to link items to (creates if not exists)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be migrated without writing",
        )

    def handle(self, *args, **options):
        tenant_slug = options["tenant"]
        client_name = options.get("client_name")
        dry_run = options.get("dry_run", False)

        try:
            tenant = Tenant.objects.get(schema_name=tenant_slug)
        except Tenant.DoesNotExist:
            raise CommandError(f"Tenant '{tenant_slug}' not found.")

        with schema_context(tenant_slug):
            self._migrate(tenant_slug, client_name, dry_run)

    def _migrate(self, tenant_slug, client_name, dry_run):
        from plaid_ingest.models import (
            PlaidItem, PlaidAccount, PlaidAccountBalance,
            PlaidTransaction, PlaidSyncCursor, PlaidWebhookEvent,
        )
        from clients.models import Client, ClientAccount

        # Resolve or create client
        tenant_client = None
        if client_name:
            tenant_client, created = Client.objects.get_or_create(name=client_name)
            if created:
                self.stdout.write(f"Created client: {client_name}")
            else:
                self.stdout.write(f"Using existing client: {client_name}")

        with connection.cursor() as cur:
            # Check if plaid schema exists
            cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'plaid'")
            if not cur.fetchone():
                raise CommandError("The 'plaid' schema does not exist in the database.")

            # --- Migrate Items ---
            cur.execute("""
                SELECT item_id, environment, access_token, institution_id, institution_name,
                       created_at, last_sync_at
                FROM plaid.items
            """)
            items_rows = cur.fetchall()
            self.stdout.write(f"Found {len(items_rows)} items to migrate")

            if dry_run:
                self._show_counts(cur)
                return

            item_map = {}  # old item_id -> PlaidItem
            for row in items_rows:
                item_id, environment, access_token, inst_id, inst_name, created_at, last_sync = row
                plaid_item, created = PlaidItem.objects.update_or_create(
                    item_id=item_id,
                    defaults={
                        "access_token": access_token,
                        "environment": environment or "sandbox",
                        "institution_id": inst_id or "",
                        "institution_name": inst_name or "",
                        "client": tenant_client,
                        "status": PlaidItem.Status.ACTIVE,
                        "last_sync_at": last_sync,
                    },
                )
                item_map[item_id] = plaid_item
                # Register in webhook tenant map
                cur.execute("""
                    INSERT INTO public.webhook_item_tenant_map (item_id, tenant_schema, created_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (item_id) DO UPDATE SET tenant_schema = EXCLUDED.tenant_schema
                """, [item_id, tenant_slug])

                self.stdout.write(f"  Item: {inst_name} ({item_id[:12]}...) {'created' if created else 'updated'}")

            # --- Migrate Accounts ---
            cur.execute("""
                SELECT account_id, item_id, name, official_name, type, subtype, mask,
                       iso_currency_code, created_at
                FROM plaid.accounts
            """)
            acct_rows = cur.fetchall()
            self.stdout.write(f"Found {len(acct_rows)} accounts to migrate")

            acct_map = {}  # old account_id -> PlaidAccount
            for row in acct_rows:
                acct_id, item_id, name, official, atype, subtype, mask, currency, created = row
                plaid_item = item_map.get(item_id)
                if not plaid_item:
                    self.stderr.write(f"  Skipping account {acct_id}: item {item_id} not found")
                    continue

                plaid_acct, created_flag = PlaidAccount.objects.update_or_create(
                    account_id=acct_id,
                    defaults={
                        "item": plaid_item,
                        "name": name or "",
                        "official_name": official or "",
                        "type": atype or "",
                        "subtype": subtype or "",
                        "mask": mask or "",
                        "iso_currency_code": currency or "USD",
                    },
                )
                acct_map[acct_id] = plaid_acct

                # Auto-create ClientAccount mapping
                if tenant_client:
                    ClientAccount.objects.get_or_create(
                        client=tenant_client,
                        account_id=acct_id,
                    )

            # --- Migrate Balances ---
            cur.execute("""
                SELECT account_id, current_balance, available_balance, credit_limit,
                       credit_remaining, iso_currency_code, as_of
                FROM plaid.account_balance_current
            """)
            bal_rows = cur.fetchall()
            self.stdout.write(f"Found {len(bal_rows)} balance records to migrate")

            for row in bal_rows:
                acct_id, current, available, limit, remaining, currency, as_of = row
                plaid_acct = acct_map.get(acct_id)
                if not plaid_acct:
                    continue
                PlaidAccountBalance.objects.update_or_create(
                    account=plaid_acct,
                    defaults={
                        "current_balance": current,
                        "available_balance": available,
                        "credit_limit": limit,
                        "credit_remaining": remaining,
                        "iso_currency_code": currency or "USD",
                    },
                )

            # --- Migrate Transactions ---
            cur.execute("SELECT COUNT(*) FROM plaid.transactions")
            txn_count = cur.fetchone()[0]
            self.stdout.write(f"Found {txn_count} transactions to migrate")

            cur.execute("""
                SELECT transaction_id, item_id, account_id, name, merchant_name, amount,
                       iso_currency_code, date, authorized_date, datetime, authorized_datetime,
                       pending, payment_channel, transaction_type, category_id,
                       personal_finance_category, location, payment_meta, counterparties,
                       logo_url, website, created_at
                FROM plaid.transactions
            """)
            batch_size = 500
            migrated = 0
            while True:
                rows = cur.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    (txn_id, item_id, acct_id, name, merchant, amount, currency,
                     date, auth_date, dt, auth_dt, pending, channel, txn_type,
                     cat_id, pfc, location, pay_meta, counterparties,
                     logo, website, created) = row

                    plaid_acct = acct_map.get(acct_id)
                    plaid_item = item_map.get(item_id)
                    if not plaid_acct or not plaid_item:
                        continue

                    PlaidTransaction.objects.update_or_create(
                        transaction_id=txn_id,
                        defaults={
                            "account": plaid_acct,
                            "item": plaid_item,
                            "amount": amount,
                            "name": name or "",
                            "merchant_name": merchant or "",
                            "date": date,
                            "authorized_date": auth_date,
                            "datetime": dt,
                            "authorized_datetime": auth_dt,
                            "pending": pending or False,
                            "payment_channel": channel or "",
                            "transaction_type": txn_type or "",
                            "category_id": cat_id or "",
                            "personal_finance_category": pfc,
                            "location": location,
                            "payment_meta": pay_meta,
                            "counterparties": counterparties,
                            "iso_currency_code": currency or "USD",
                            "logo_url": logo or "",
                            "website": website or "",
                        },
                    )
                    migrated += 1

                self.stdout.write(f"  Migrated {migrated}/{txn_count} transactions...")

            # --- Migrate Sync Cursor ---
            cur.execute("SELECT item_id, cursor, has_more, last_synced_at FROM plaid.transaction_sync_state")
            for row in cur.fetchall():
                item_id, cursor_val, has_more, last_synced = row
                plaid_item = item_map.get(item_id)
                if plaid_item:
                    PlaidSyncCursor.objects.update_or_create(
                        item=plaid_item,
                        defaults={
                            "cursor": cursor_val or "",
                            "has_more": has_more or False,
                            "last_synced_at": last_synced,
                        },
                    )

            self.stdout.write(self.style.SUCCESS(
                f"\nMigration complete!\n"
                f"  Items: {len(item_map)}\n"
                f"  Accounts: {len(acct_map)}\n"
                f"  Balances: {len(bal_rows)}\n"
                f"  Transactions: {migrated}\n"
            ))

    def _show_counts(self, cur):
        """Show counts for dry run."""
        for table in ["items", "accounts", "account_balance_current", "transactions",
                       "transaction_sync_state", "webhook_events"]:
            cur.execute(f"SELECT COUNT(*) FROM plaid.{table}")
            count = cur.fetchone()[0]
            self.stdout.write(f"  plaid.{table}: {count} rows")
