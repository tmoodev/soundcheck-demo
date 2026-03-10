"""
Plaid ingest models – tenant-scoped.
Stores Plaid items, accounts, balances, transactions, sync state, and webhook events.
"""
import uuid

from django.db import models

from clients.models import Client
from .encryption import EncryptedTextField


# ---------------------------------------------------------------------------
# Plaid Item (a bank connection via Plaid Link)
# ---------------------------------------------------------------------------
class PlaidItem(models.Model):
    """A Plaid Item represents a user's connection to a single financial institution."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ERROR = "error", "Error"
        REVOKED = "revoked", "Revoked"

    class Environment(models.TextChoices):
        SANDBOX = "sandbox", "Sandbox"
        DEVELOPMENT = "development", "Development"
        PRODUCTION = "production", "Production"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item_id = models.TextField(unique=True, help_text="Plaid item_id")
    access_token = EncryptedTextField(help_text="Plaid access_token (encrypted)")
    environment = models.CharField(
        max_length=20, choices=Environment.choices, default=Environment.SANDBOX
    )
    institution_id = models.TextField(blank=True, default="")
    institution_name = models.TextField(blank=True, default="")
    client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plaid_items",
        help_text="Client this item belongs to",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    error_code = models.TextField(blank=True, default="")
    consent_expires_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "plaid_ingest"
        db_table = "plaid_item"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.institution_name} ({self.item_id[:12]}...)"


# ---------------------------------------------------------------------------
# Plaid Account
# ---------------------------------------------------------------------------
class PlaidAccount(models.Model):
    """A financial account within a Plaid Item."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account_id = models.TextField(unique=True, help_text="Plaid account_id")
    item = models.ForeignKey(
        PlaidItem, on_delete=models.CASCADE, related_name="accounts"
    )
    name = models.TextField(blank=True, default="")
    official_name = models.TextField(blank=True, default="")
    type = models.TextField(blank=True, default="", help_text="depository, credit, loan, investment, etc.")
    subtype = models.TextField(blank=True, default="")
    mask = models.TextField(blank=True, default="", help_text="Last 4 digits")
    iso_currency_code = models.TextField(blank=True, default="USD")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "plaid_ingest"
        db_table = "plaid_account"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.mask})"


# ---------------------------------------------------------------------------
# Plaid Account Balance (current snapshot)
# ---------------------------------------------------------------------------
class PlaidAccountBalance(models.Model):
    """Current balance for a Plaid account. One-to-one with PlaidAccount."""

    account = models.OneToOneField(
        PlaidAccount, on_delete=models.CASCADE, primary_key=True, related_name="balance"
    )
    current_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    available_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    credit_remaining = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    iso_currency_code = models.TextField(blank=True, default="USD")
    as_of = models.DateTimeField(auto_now=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "plaid_ingest"
        db_table = "plaid_account_balance"

    def __str__(self):
        return f"Balance for {self.account}"


# ---------------------------------------------------------------------------
# Plaid Transaction
# ---------------------------------------------------------------------------
class PlaidTransaction(models.Model):
    """A single financial transaction from Plaid."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id = models.TextField(unique=True, help_text="Plaid transaction_id")
    account = models.ForeignKey(
        PlaidAccount, on_delete=models.CASCADE, related_name="transactions"
    )
    item = models.ForeignKey(
        PlaidItem, on_delete=models.CASCADE, related_name="transactions"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    name = models.TextField(blank=True, default="")
    merchant_name = models.TextField(blank=True, default="")
    date = models.DateField(null=True, blank=True)
    authorized_date = models.DateField(null=True, blank=True)
    datetime = models.DateTimeField(null=True, blank=True)
    authorized_datetime = models.DateTimeField(null=True, blank=True)
    pending = models.BooleanField(default=False)
    payment_channel = models.TextField(blank=True, default="")
    transaction_type = models.TextField(blank=True, default="")
    category_id = models.TextField(blank=True, default="")
    personal_finance_category = models.JSONField(null=True, blank=True)
    location = models.JSONField(null=True, blank=True)
    payment_meta = models.JSONField(null=True, blank=True)
    counterparties = models.JSONField(null=True, blank=True)
    iso_currency_code = models.TextField(blank=True, default="USD")
    logo_url = models.TextField(blank=True, default="")
    website = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "plaid_ingest"
        db_table = "plaid_transaction"
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["-date"], name="idx_plaidtxn_date"),
            models.Index(fields=["account", "-date"], name="idx_plaidtxn_acct_date"),
            models.Index(fields=["pending"], name="idx_plaidtxn_pending"),
        ]

    def __str__(self):
        return f"{self.name} ({self.amount}) on {self.date}"


# ---------------------------------------------------------------------------
# Sync Cursor (for /transactions/sync)
# ---------------------------------------------------------------------------
class PlaidSyncCursor(models.Model):
    """Tracks the cursor for Plaid's /transactions/sync endpoint."""

    item = models.OneToOneField(
        PlaidItem, on_delete=models.CASCADE, primary_key=True, related_name="sync_cursor"
    )
    cursor = models.TextField(blank=True, default="")
    has_more = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "plaid_ingest"
        db_table = "plaid_sync_cursor"

    def __str__(self):
        return f"Cursor for {self.item}"


# ---------------------------------------------------------------------------
# Webhook Events (for idempotency and audit)
# ---------------------------------------------------------------------------
class PlaidWebhookEvent(models.Model):
    """Log of received Plaid webhook events."""

    id = models.BigAutoField(primary_key=True)
    received_at = models.DateTimeField(auto_now_add=True)
    item_id = models.TextField(blank=True, default="")
    webhook_type = models.TextField()
    webhook_code = models.TextField()
    request_id = models.TextField(blank=True, default="")
    event_hash = models.TextField(unique=True, help_text="SHA-256 of payload for dedup")
    is_duplicate = models.BooleanField(default=False)
    duplicate_of_id = models.BigIntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict)

    class Meta:
        app_label = "plaid_ingest"
        db_table = "plaid_webhook_event"
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.webhook_type}.{self.webhook_code} at {self.received_at}"
