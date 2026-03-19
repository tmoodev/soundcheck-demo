"""
Core business logic for Plaid integration.
Handles Link token creation, token exchange, account fetching,
transaction sync, and balance refresh.
"""
import hashlib
import logging
from decimal import Decimal

from django.conf import settings
from django.db import connection
from django.utils import timezone

import plaid
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.accounts_get_request import AccountsGetRequest

from clients.models import Client, ClientAccount
from .models import (
    PlaidItem,
    PlaidAccount,
    PlaidAccountBalance,
    PlaidTransaction,
    PlaidSyncCursor,
)
from .plaid_client import get_plaid_client, get_plaid_env_str

logger = logging.getLogger("soundcheck")


# ---------------------------------------------------------------------------
# Link Token
# ---------------------------------------------------------------------------
def create_link_token(user_id: str, client_id: str = None) -> str:
    """
    Create a Plaid Link token for the frontend.
    Returns the link_token string.
    """
    client = get_plaid_client()

    # Build webhook URL
    webhook_url = getattr(settings, "PLAID_WEBHOOK_URL", "")

    request = LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(client_user_id=str(user_id)),
        client_name="SoundCheck Financial",
        products=[Products("transactions")],
        country_codes=[CountryCode("US")],
        language="en",
        webhook=webhook_url if webhook_url else None,
    )

    response = client.link_token_create(request)
    return response.link_token


# ---------------------------------------------------------------------------
# Token Exchange & Account Fetch
# ---------------------------------------------------------------------------
def exchange_public_token(public_token: str, client_id: str = None) -> PlaidItem:
    """
    Exchange a Plaid public_token for an access_token.
    Creates the PlaidItem, fetches accounts, and triggers initial sync.
    Returns the created PlaidItem.
    """
    plaid_client = get_plaid_client()

    # Exchange token
    exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
    exchange_response = plaid_client.item_public_token_exchange(exchange_request)

    access_token = exchange_response.access_token
    item_id = exchange_response.item_id

    # Get item details (institution info)
    item_response = plaid_client.item_get(
        plaid.model.item_get_request.ItemGetRequest(access_token=access_token)
    )
    institution_id = item_response.item.institution_id or ""
    institution_name = ""

    if institution_id:
        try:
            inst_response = plaid_client.institutions_get_by_id(
                plaid.model.institutions_get_by_id_request.InstitutionsGetByIdRequest(
                    institution_id=institution_id,
                    country_codes=[CountryCode("US")],
                )
            )
            institution_name = inst_response.institution.name
        except Exception:
            logger.warning(f"Could not fetch institution name for {institution_id}")

    # Resolve client if provided
    tenant_client = None
    if client_id:
        try:
            tenant_client = Client.objects.get(client_id=client_id)
        except Client.DoesNotExist:
            logger.warning(f"Client {client_id} not found, creating item without client link")

    # Create PlaidItem
    plaid_item = PlaidItem.objects.create(
        item_id=item_id,
        access_token=access_token,
        environment=get_plaid_env_str(),
        institution_id=institution_id,
        institution_name=institution_name,
        client=tenant_client,
        status=PlaidItem.Status.ACTIVE,
    )

    # Register in webhook tenant map (public schema)
    _register_webhook_tenant_map(item_id)

    # Fetch accounts and balances
    fetch_accounts(plaid_item)

    # Auto-create ClientAccount mappings if client is set
    if tenant_client:
        _create_client_account_mappings(plaid_item, tenant_client)

    # Trigger initial transaction sync
    sync_transactions(plaid_item)

    return plaid_item


def fetch_accounts(plaid_item: PlaidItem):
    """Fetch accounts and balances from Plaid for the given item."""
    plaid_client = get_plaid_client()

    request = AccountsGetRequest(access_token=plaid_item.access_token)
    response = plaid_client.accounts_get(request)

    for acct in response.accounts:
        plaid_account, _ = PlaidAccount.objects.update_or_create(
            account_id=acct.account_id,
            defaults={
                "item": plaid_item,
                "name": acct.name or "",
                "official_name": acct.official_name or "",
                "type": str(acct.type) if acct.type else "",
                "subtype": str(acct.subtype) if acct.subtype else "",
                "mask": acct.mask or "",
                "iso_currency_code": acct.balances.iso_currency_code or "USD",
            },
        )

        # Upsert balance
        balances = acct.balances
        PlaidAccountBalance.objects.update_or_create(
            account=plaid_account,
            defaults={
                "current_balance": _to_decimal(balances.current),
                "available_balance": _to_decimal(balances.available),
                "credit_limit": _to_decimal(balances.limit),
                "credit_remaining": (
                    _to_decimal(balances.limit) - _to_decimal(balances.current)
                    if balances.limit and balances.current else None
                ),
                "iso_currency_code": balances.iso_currency_code or "USD",
            },
        )

    plaid_item.last_sync_at = timezone.now()
    plaid_item.save(update_fields=["last_sync_at", "updated_at"])

    logger.info(f"Fetched {len(response.accounts)} accounts for item {plaid_item.item_id[:12]}")


# ---------------------------------------------------------------------------
# Transaction Sync (cursor-based)
# ---------------------------------------------------------------------------
def sync_transactions(plaid_item: PlaidItem) -> dict:
    """
    Incremental sync using Plaid's /transactions/sync endpoint.
    Returns a summary dict with counts of added, modified, removed.
    """
    plaid_client = get_plaid_client()

    # Get current cursor
    try:
        sync_state = plaid_item.sync_cursor
        cursor = sync_state.cursor
    except PlaidSyncCursor.DoesNotExist:
        cursor = ""

    added_count = 0
    modified_count = 0
    removed_count = 0

    while True:
        request_kwargs = {"access_token": plaid_item.access_token}
        if cursor:
            request_kwargs["cursor"] = cursor
        request = TransactionsSyncRequest(**request_kwargs)
        response = plaid_client.transactions_sync(request)

        # Process added transactions
        for txn in response.added:
            _upsert_transaction(plaid_item, txn)
            added_count += 1

        # Process modified transactions
        for txn in response.modified:
            _upsert_transaction(plaid_item, txn)
            modified_count += 1

        # Process removed transactions
        for removed in response.removed:
            PlaidTransaction.objects.filter(
                transaction_id=removed.transaction_id
            ).delete()
            removed_count += 1

        cursor = response.next_cursor

        # Save cursor state
        PlaidSyncCursor.objects.update_or_create(
            item=plaid_item,
            defaults={
                "cursor": cursor,
                "has_more": response.has_more,
                "last_synced_at": timezone.now(),
            },
        )

        if not response.has_more:
            break

    plaid_item.last_sync_at = timezone.now()
    plaid_item.save(update_fields=["last_sync_at", "updated_at"])

    logger.info(
        f"Sync complete for {plaid_item.item_id[:12]}: "
        f"+{added_count} ~{modified_count} -{removed_count}"
    )

    return {
        "added": added_count,
        "modified": modified_count,
        "removed": removed_count,
    }


# ---------------------------------------------------------------------------
# Balance Refresh
# ---------------------------------------------------------------------------
def refresh_balances(plaid_item: PlaidItem):
    """Refresh account balances for all accounts in the given item."""
    fetch_accounts(plaid_item)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _upsert_transaction(plaid_item: PlaidItem, txn):
    """Create or update a PlaidTransaction from a Plaid API transaction object."""
    # Resolve the PlaidAccount
    try:
        plaid_account = PlaidAccount.objects.get(account_id=txn.account_id)
    except PlaidAccount.DoesNotExist:
        logger.warning(
            f"Account {txn.account_id} not found for transaction {txn.transaction_id}, "
            f"fetching accounts first"
        )
        fetch_accounts(plaid_item)
        try:
            plaid_account = PlaidAccount.objects.get(account_id=txn.account_id)
        except PlaidAccount.DoesNotExist:
            logger.error(f"Account {txn.account_id} still not found, skipping transaction")
            return

    PlaidTransaction.objects.update_or_create(
        transaction_id=txn.transaction_id,
        defaults={
            "account": plaid_account,
            "item": plaid_item,
            "amount": _to_decimal(txn.amount),
            "name": txn.name or "",
            "merchant_name": txn.merchant_name or "",
            "date": txn.date,
            "authorized_date": txn.authorized_date,
            "datetime": getattr(txn, "datetime", None),
            "authorized_datetime": getattr(txn, "authorized_datetime", None),
            "pending": txn.pending or False,
            "payment_channel": str(txn.payment_channel) if txn.payment_channel else "",
            "transaction_type": str(txn.transaction_type) if txn.transaction_type else "",
            "category_id": txn.category_id or "",
            "personal_finance_category": (
                txn.personal_finance_category.to_dict()
                if txn.personal_finance_category else None
            ),
            "location": txn.location.to_dict() if txn.location else None,
            "payment_meta": txn.payment_meta.to_dict() if txn.payment_meta else None,
            "counterparties": (
                [c.to_dict() for c in txn.counterparties]
                if txn.counterparties else None
            ),
            "iso_currency_code": txn.iso_currency_code or "USD",
            "logo_url": txn.logo_url or "",
            "website": txn.website or "",
        },
    )


def _to_decimal(value) -> Decimal | None:
    """Safely convert a value to Decimal."""
    if value is None:
        return None
    return Decimal(str(value))


def _create_client_account_mappings(plaid_item: PlaidItem, tenant_client: Client):
    """Create ClientAccount records linking a client to the item's accounts."""
    for plaid_account in plaid_item.accounts.all():
        ClientAccount.objects.get_or_create(
            client=tenant_client,
            account_id=plaid_account.account_id,
        )


def _register_webhook_tenant_map(item_id: str):
    """Register the item_id -> tenant mapping in the public schema for webhook routing."""
    tenant_schema = connection.schema_name
    try:
        from django.db import connection as conn
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.webhook_item_tenant_map (item_id, tenant_schema, created_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (item_id) DO UPDATE SET tenant_schema = EXCLUDED.tenant_schema
                """,
                [item_id, tenant_schema],
            )
    except Exception:
        logger.exception(f"Failed to register webhook tenant map for item {item_id}")


def compute_webhook_event_hash(payload: dict) -> str:
    """Compute a SHA-256 hash of a webhook payload for dedup."""
    import json
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()
