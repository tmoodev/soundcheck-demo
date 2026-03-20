from django.urls import path
from . import admin_views

app_name = "admin_panel"

urlpatterns = [
    # User management
    path("users/", admin_views.user_list_view, name="user_list"),
    path("users/create/", admin_views.user_create_view, name="user_create"),
    path("users/<uuid:user_id>/edit/", admin_views.user_edit_view, name="user_edit"),
    # Client management
    path("clients/", admin_views.client_list_view, name="client_list"),
    path("clients/create/", admin_views.client_create_view, name="client_create"),
    path("clients/<uuid:client_id>/edit/", admin_views.client_edit_view, name="client_edit"),
    path("clients/<uuid:client_id>/mappings/", admin_views.client_mappings_view, name="client_mappings"),
    path("clients/<uuid:client_id>/mappings/<int:mapping_id>/delete/",
         admin_views.client_mapping_delete_view, name="client_mapping_delete"),

    # Bank connections (Plaid)
    path("banks/", admin_views.plaid_items_view, name="plaid_items"),
    path("banks/connect/", admin_views.plaid_connect_view, name="plaid_connect"),

    # Audit log
    path("audit/", admin_views.audit_log_view, name="audit_log"),
]
