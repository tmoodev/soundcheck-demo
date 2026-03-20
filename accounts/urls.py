from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
path("password-reset/", views.password_reset_request_view, name="password_reset"),
    path("password-reset/confirm/<str:token>/", views.password_reset_confirm_view, name="password_reset_confirm"),
]
