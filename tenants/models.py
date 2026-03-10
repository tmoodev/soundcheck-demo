"""Tenant models for django-tenants schema-per-tenant isolation."""
import uuid
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class Tenant(TenantMixin):
    """Each tenant maps to one Postgres schema."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Display name for the tenant org")
    slug = models.SlugField(max_length=63, unique=True, help_text="Subdomain slug")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    auto_create_schema = True

    class Meta:
        app_label = "tenants"

    def __str__(self):
        return self.name


class Domain(DomainMixin):
    """Domain → tenant mapping. Primary domain used for routing."""

    class Meta:
        app_label = "tenants"

    def __str__(self):
        return self.domain


class WebhookItemTenantMap(models.Model):
    """
    Public-schema lookup table mapping Plaid item_id to tenant schema.
    Used by the webhook endpoint to resolve which tenant a webhook belongs to.
    """
    item_id = models.TextField(primary_key=True, help_text="Plaid item_id")
    tenant_schema = models.CharField(max_length=63, help_text="Tenant schema name")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "tenants"
        db_table = "webhook_item_tenant_map"

    def __str__(self):
        return f"{self.item_id[:16]} → {self.tenant_schema}"
