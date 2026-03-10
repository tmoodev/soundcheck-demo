"""
Plaid SDK client factory.
Reads configuration from Django settings and returns a configured Plaid API client.
"""
import plaid
from plaid.api import plaid_api
from django.conf import settings


_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "development": plaid.Environment.Sandbox,  # Plaid SDK v38+ only has Sandbox/Production
    "production": plaid.Environment.Production,
}


def get_plaid_client() -> plaid_api.PlaidApi:
    """Return a configured Plaid API client."""
    configuration = plaid.Configuration(
        host=_ENV_MAP.get(settings.PLAID_ENV, plaid.Environment.Sandbox),
        api_key={
            "clientId": settings.PLAID_CLIENT_ID,
            "secret": settings.PLAID_SECRET,
        },
    )
    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


def get_plaid_env_str() -> str:
    """Return the current Plaid environment string."""
    return getattr(settings, "PLAID_ENV", "sandbox")
