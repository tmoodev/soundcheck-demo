"""
API views for Plaid integration.
All tenant-scoped endpoints require authentication and admin role.
"""
import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

from dashboard.decorators import tenant_admin_required
from .models import PlaidItem
from . import services

logger = logging.getLogger("soundcheck")


# ---------------------------------------------------------------------------
# Plaid Link Token
# ---------------------------------------------------------------------------
@login_required
@tenant_admin_required
@require_POST
def create_link_token(request):
    """Create a Plaid Link token for the frontend."""
    try:
        body = json.loads(request.body) if request.body else {}
        client_id = body.get("client_id")

        link_token = services.create_link_token(
            user_id=str(request.user.id),
            client_id=client_id,
        )
        return JsonResponse({"link_token": link_token})

    except Exception as e:
        logger.exception("Error creating link token")
        return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# Exchange Public Token
# ---------------------------------------------------------------------------
@login_required
@tenant_admin_required
@require_POST
def exchange_token(request):
    """Exchange a Plaid public_token for an access_token and onboard the item."""
    try:
        body = json.loads(request.body)
        public_token = body.get("public_token")
        client_id = body.get("client_id")

        if not public_token:
            return JsonResponse({"error": "public_token is required"}, status=400)

        plaid_item = services.exchange_public_token(
            public_token=public_token,
            client_id=client_id,
        )

        return JsonResponse({
            "item_id": plaid_item.item_id,
            "institution_name": plaid_item.institution_name,
            "accounts_count": plaid_item.accounts.count(),
            "status": plaid_item.status,
        })

    except Exception as e:
        logger.exception("Error exchanging public token")
        return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# List Items
# ---------------------------------------------------------------------------
@login_required
@tenant_admin_required
@require_GET
def list_items(request):
    """List all Plaid items for the current tenant."""
    items = PlaidItem.objects.all().select_related("client")
    data = []
    for item in items:
        data.append({
            "id": str(item.id),
            "item_id": item.item_id,
            "institution_name": item.institution_name,
            "institution_id": item.institution_id,
            "client_name": item.client.name if item.client else None,
            "client_id": str(item.client.client_id) if item.client else None,
            "status": item.status,
            "accounts_count": item.accounts.count(),
            "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
            "created_at": item.created_at.isoformat(),
        })
    return JsonResponse({"items": data})


# ---------------------------------------------------------------------------
# Manual Sync
# ---------------------------------------------------------------------------
@login_required
@tenant_admin_required
@require_POST
def sync_item(request, item_id):
    """Trigger a manual transaction sync for a specific item."""
    try:
        plaid_item = PlaidItem.objects.get(id=item_id)
        result = services.sync_transactions(plaid_item)
        return JsonResponse({
            "status": "ok",
            "item_id": plaid_item.item_id,
            **result,
        })
    except PlaidItem.DoesNotExist:
        return JsonResponse({"error": "Item not found"}, status=404)
    except Exception as e:
        logger.exception(f"Error syncing item {item_id}")
        return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# Refresh Balances
# ---------------------------------------------------------------------------
@login_required
@tenant_admin_required
@require_POST
def refresh_balances(request, item_id):
    """Refresh balances for all accounts in a specific item."""
    try:
        plaid_item = PlaidItem.objects.get(id=item_id)
        services.refresh_balances(plaid_item)
        return JsonResponse({
            "status": "ok",
            "item_id": plaid_item.item_id,
        })
    except PlaidItem.DoesNotExist:
        return JsonResponse({"error": "Item not found"}, status=404)
    except Exception as e:
        logger.exception(f"Error refreshing balances for item {item_id}")
        return JsonResponse({"error": str(e)}, status=500)
