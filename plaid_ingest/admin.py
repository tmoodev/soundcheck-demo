from django.contrib import admin
from .models import (
    PlaidItem,
    PlaidAccount,
    PlaidAccountBalance,
    PlaidTransaction,
    PlaidSyncCursor,
    PlaidWebhookEvent,
)


class PlaidAccountInline(admin.TabularInline):
    model = PlaidAccount
    extra = 0
    readonly_fields = ("account_id", "name", "type", "subtype", "mask")
    fields = ("account_id", "name", "type", "subtype", "mask")


@admin.register(PlaidItem)
class PlaidItemAdmin(admin.ModelAdmin):
    list_display = ("institution_name", "item_id_short", "client", "status", "last_sync_at", "created_at")
    list_filter = ("status", "environment")
    search_fields = ("institution_name", "item_id")
    readonly_fields = ("item_id", "environment", "created_at", "updated_at")
    inlines = [PlaidAccountInline]

    def item_id_short(self, obj):
        return obj.item_id[:16] + "..."
    item_id_short.short_description = "Item ID"


@admin.register(PlaidAccount)
class PlaidAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "subtype", "mask", "item")
    list_filter = ("type",)
    search_fields = ("name", "account_id", "mask")


@admin.register(PlaidTransaction)
class PlaidTransactionAdmin(admin.ModelAdmin):
    list_display = ("name", "amount", "date", "pending", "account", "merchant_name")
    list_filter = ("pending", "payment_channel")
    search_fields = ("name", "merchant_name", "transaction_id")
    date_hierarchy = "date"


@admin.register(PlaidWebhookEvent)
class PlaidWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("webhook_type", "webhook_code", "item_id_short", "is_duplicate", "received_at")
    list_filter = ("webhook_type", "is_duplicate")
    readonly_fields = ("payload",)

    def item_id_short(self, obj):
        return obj.item_id[:16] + "..." if obj.item_id else ""
    item_id_short.short_description = "Item ID"
