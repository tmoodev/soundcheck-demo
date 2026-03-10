"""
Plaid webhook receiver and dispatcher.
This endpoint runs in the public schema context and manually resolves
the tenant from the item_id in the webhook payload.
"""
import json
import logging

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from django_tenants.utils import schema_context

from .models import PlaidItem, PlaidWebhookEvent
from .services import sync_transactions, refresh_balances, compute_webhook_event_hash

logger = logging.getLogger("soundcheck")


def _resolve_tenant_schema(item_id: str) -> str | None:
    """Look up the tenant schema for a given Plaid item_id from the public mapping table."""
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT tenant_schema FROM public.webhook_item_tenant_map WHERE item_id = %s",
                [item_id],
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        logger.exception(f"Error looking up tenant for item_id {item_id}")
        return None


@csrf_exempt
@require_POST
def plaid_webhook(request):
    """
    Receive a Plaid webhook, resolve the tenant, and dispatch.
    This endpoint is unauthenticated (Plaid sends it directly).
    Idempotency is ensured via event_hash dedup.
    """
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    webhook_type = payload.get("webhook_type", "")
    webhook_code = payload.get("webhook_code", "")
    item_id = payload.get("item_id", "")
    request_id = payload.get("request_id", "")

    logger.info(f"Webhook received: {webhook_type}.{webhook_code} for item {item_id[:12] if item_id else 'N/A'}")

    if not item_id:
        return JsonResponse({"error": "No item_id in payload"}, status=400)

    # Resolve tenant
    tenant_schema = _resolve_tenant_schema(item_id)
    if not tenant_schema:
        logger.warning(f"No tenant found for item_id {item_id}")
        return JsonResponse({"error": "Unknown item_id"}, status=404)

    # Process within tenant context
    with schema_context(tenant_schema):
        # Dedup check
        event_hash = compute_webhook_event_hash(payload)

        existing = PlaidWebhookEvent.objects.filter(event_hash=event_hash).first()
        if existing:
            PlaidWebhookEvent.objects.create(
                item_id=item_id,
                webhook_type=webhook_type,
                webhook_code=webhook_code,
                request_id=request_id,
                event_hash=event_hash + "_dup",
                is_duplicate=True,
                duplicate_of_id=existing.id,
                payload=payload,
            )
            logger.info(f"Duplicate webhook event {event_hash[:12]}, skipping")
            return JsonResponse({"status": "duplicate"})

        # Log the event
        event = PlaidWebhookEvent.objects.create(
            item_id=item_id,
            webhook_type=webhook_type,
            webhook_code=webhook_code,
            request_id=request_id,
            event_hash=event_hash,
            is_duplicate=False,
            payload=payload,
        )

        # Dispatch
        try:
            _dispatch_webhook(item_id, webhook_type, webhook_code, payload)
        except Exception:
            logger.exception(f"Error dispatching webhook {webhook_type}.{webhook_code}")

    return JsonResponse({"status": "ok"})


def _dispatch_webhook(item_id: str, webhook_type: str, webhook_code: str, payload: dict):
    """Route webhook events to the appropriate handler."""
    try:
        plaid_item = PlaidItem.objects.get(item_id=item_id)
    except PlaidItem.DoesNotExist:
        logger.error(f"PlaidItem not found for item_id {item_id}")
        return

    if webhook_type == "TRANSACTIONS":
        if webhook_code in ("SYNC_UPDATES_AVAILABLE", "DEFAULT_UPDATE", "INITIAL_UPDATE"):
            logger.info(f"Syncing transactions for item {item_id[:12]}")
            sync_transactions(plaid_item)
        elif webhook_code == "TRANSACTIONS_REMOVED":
            logger.info(f"Transactions removed event for item {item_id[:12]}, syncing")
            sync_transactions(plaid_item)
        else:
            logger.info(f"Unhandled TRANSACTIONS webhook code: {webhook_code}")

    elif webhook_type == "ITEM":
        if webhook_code == "ERROR":
            error = payload.get("error", {})
            error_code = error.get("error_code", "UNKNOWN")
            plaid_item.status = PlaidItem.Status.ERROR
            plaid_item.error_code = error_code
            plaid_item.save(update_fields=["status", "error_code", "updated_at"])
            logger.warning(f"Item {item_id[:12]} entered error state: {error_code}")

        elif webhook_code == "PENDING_EXPIRATION":
            consent_expires = payload.get("consent_expiration_time")
            if consent_expires:
                from django.utils.dateparse import parse_datetime
                plaid_item.consent_expires_at = parse_datetime(consent_expires)
                plaid_item.save(update_fields=["consent_expires_at", "updated_at"])
            logger.warning(f"Item {item_id[:12]} consent expiring")

        elif webhook_code == "USER_PERMISSION_REVOKED":
            plaid_item.status = PlaidItem.Status.REVOKED
            plaid_item.save(update_fields=["status", "updated_at"])
            logger.warning(f"Item {item_id[:12]} permission revoked by user")

        else:
            logger.info(f"Unhandled ITEM webhook code: {webhook_code}")

    elif webhook_type == "HOLDINGS":
        logger.info(f"Holdings webhook received (not yet implemented): {webhook_code}")

    elif webhook_type == "INVESTMENTS_TRANSACTIONS":
        logger.info(f"Investment transactions webhook received (not yet implemented): {webhook_code}")

    else:
        logger.info(f"Unhandled webhook type: {webhook_type}.{webhook_code}")
