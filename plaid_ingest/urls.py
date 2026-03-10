"""URL patterns for Plaid ingest API (tenant-scoped endpoints)."""
from django.urls import path
from . import views

app_name = "plaid_ingest"

urlpatterns = [
    # Plaid Link
    path("link-token/", views.create_link_token, name="create_link_token"),
    path("exchange-token/", views.exchange_token, name="exchange_token"),

    # Item management
    path("items/", views.list_items, name="list_items"),
    path("items/<uuid:item_id>/sync/", views.sync_item, name="sync_item"),
    path("items/<uuid:item_id>/refresh-balances/", views.refresh_balances, name="refresh_balances"),
]
