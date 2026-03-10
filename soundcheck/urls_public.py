"""URL configuration for the public schema (no tenant).
Displays a simple landing/error page and hosts the Plaid webhook endpoint.
"""
from pathlib import Path

from django.http import HttpResponse, FileResponse
from django.urls import path

from plaid_ingest.webhook import plaid_webhook


def public_landing(request):
    return HttpResponse(
        "<h1>SoundCheck Financial</h1>"
        "<p>Please access your tenant dashboard via your organization's subdomain.</p>",
        content_type="text/html",
    )


def download_agent_md(request):
    filepath = Path(__file__).resolve().parent.parent / "agent.md"
    if filepath.exists():
        return FileResponse(
            open(filepath, "rb"),
            content_type="text/markdown",
            as_attachment=True,
            filename="agent.md",
        )
    return HttpResponse("Not found", status=404)


urlpatterns = [
    path("", public_landing),
    path("api/plaid/webhook/", plaid_webhook, name="plaid_webhook"),
    path("download/agent.md", download_agent_md, name="download_agent_md"),
]
