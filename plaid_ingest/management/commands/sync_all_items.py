"""
Management command to sync transactions for all active Plaid items across all tenants.
Suitable for running via cron.

Usage:
    python manage.py sync_all_items
    python manage.py sync_all_items --tenant moore
"""
import logging

from django.core.management.base import BaseCommand
from django.db import connection

from django_tenants.utils import schema_context
from tenants.models import Tenant

logger = logging.getLogger("soundcheck")


class Command(BaseCommand):
    help = "Sync transactions for all active Plaid items across all tenants."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            type=str,
            default=None,
            help="Only sync items for a specific tenant (by slug/schema_name)",
        )
        parser.add_argument(
            "--balances",
            action="store_true",
            help="Also refresh account balances",
        )

    def handle(self, *args, **options):
        tenant_slug = options.get("tenant")
        refresh_balances = options.get("balances", False)

        if tenant_slug:
            tenants = Tenant.objects.filter(schema_name=tenant_slug, is_active=True)
            if not tenants.exists():
                self.stderr.write(self.style.ERROR(f"Tenant '{tenant_slug}' not found or inactive."))
                return
        else:
            tenants = Tenant.objects.filter(is_active=True).exclude(schema_name="public")

        total_synced = 0

        for tenant in tenants:
            self.stdout.write(f"Processing tenant: {tenant.name} ({tenant.schema_name})")

            with schema_context(tenant.schema_name):
                from plaid_ingest.models import PlaidItem
                from plaid_ingest.services import sync_transactions, refresh_balances as do_refresh

                items = PlaidItem.objects.filter(status=PlaidItem.Status.ACTIVE)

                for item in items:
                    try:
                        self.stdout.write(f"  Syncing {item.institution_name} ({item.item_id[:12]}...)")
                        result = sync_transactions(item)
                        self.stdout.write(
                            f"    +{result['added']} ~{result['modified']} -{result['removed']}"
                        )
                        total_synced += 1

                        if refresh_balances:
                            do_refresh(item)
                            self.stdout.write("    Balances refreshed")

                    except Exception as e:
                        self.stderr.write(
                            self.style.ERROR(f"    Error syncing item {item.item_id[:12]}: {e}")
                        )
                        logger.exception(f"Error syncing item {item.item_id}")

        self.stdout.write(self.style.SUCCESS(f"\nDone. Synced {total_synced} items."))
