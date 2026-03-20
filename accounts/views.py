"""Authentication views: login, password reset."""
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_http_methods

from django_ratelimit.decorators import ratelimit

from auditlog.services import log_event

logger = logging.getLogger(__name__)
from .forms import (
    LoginForm,
    PasswordResetRequestForm, PasswordResetConfirmForm,
)
from .models import User, PasswordResetToken


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            log_event(request, "login_success", user=user)
            return redirect(settings.LOGIN_REDIRECT_URL)
        else:
            # Log failed attempt
            email = request.POST.get("email", "")
            log_event(request, "login_failure", detail=f"Failed login for {email}")
    else:
        form = LoginForm()
    return render(request, "registration/login.html", {"form": form})


@require_http_methods(["GET", "POST"])
def logout_view(request):
    if request.method == "POST":
        logout(request)
        return redirect("accounts:login")
    return render(request, "registration/logout_confirm.html")


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------
@ratelimit(key="ip", rate="5/m", method="POST", block=True)
@require_http_methods(["GET", "POST"])
def password_reset_request_view(request):
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower()
            try:
                user = User.objects.get(email=email, is_active=True)
                token_obj = PasswordResetToken(user=user)
                token_obj.save()
                try:
                    _send_reset_email(request, user, token_obj.token)
                except Exception:
                    logger.exception("Failed to send password reset email to %s", email)
            except User.DoesNotExist:
                pass  # Do not reveal whether email exists
            messages.success(request, "If an account exists with that email, a reset link has been sent.")
            return redirect("accounts:login")
    else:
        form = PasswordResetRequestForm()
    return render(request, "registration/password_reset_request.html", {"form": form})


@require_http_methods(["GET", "POST"])
def password_reset_confirm_view(request, token):
    token_obj = get_object_or_404(PasswordResetToken, token=token)
    if not token_obj.is_valid:
        messages.error(request, "This reset link has expired or already been used.")
        return redirect("accounts:login")

    if request.method == "POST":
        form = PasswordResetConfirmForm(request.POST)
        if form.is_valid():
            user = token_obj.user
            user.set_password(form.cleaned_data["password"])
            user.save(update_fields=["password"])
            token_obj.used = True
            token_obj.save(update_fields=["used"])
            log_event(request, "password_reset_complete", user=user)
            messages.success(request, "Password has been reset. Please log in.")
            return redirect("accounts:login")
    else:
        form = PasswordResetConfirmForm()

    return render(request, "registration/password_reset_confirm.html", {"form": form, "token": token})


def _send_reset_email(request, user, token):
    """Send password reset email via configured SMTP."""
    from django.core.mail import send_mail

    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    link = f"{scheme}://{host}/auth/password-reset/confirm/{token}/"
    send_mail(
        subject="SoundCheck Financial – Password Reset",
        message=(
            f"Hi {user.display_name},\n\n"
            f"Click the link below to reset your password:\n{link}\n\n"
            f"This link expires in 1 hour.\n\n"
            f"If you didn't request this, ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
