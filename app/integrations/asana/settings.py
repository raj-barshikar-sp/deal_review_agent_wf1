"""Asana constants and registered OAuth settings."""

import os

from app.config import ENV_PATH
from app.core.env import parse_env, setting

from .errors import AsanaError

PROJECT_NAME = "TEST Deal Review Tracker"
AUTHORIZE_URL = "https://app.asana.com/-/oauth_authorize"
TOKEN_URL = "https://app.asana.com/-/oauth_token"
API_URL = "https://app.asana.com/api/1.0"
REDIRECT_URI = "http://127.0.0.1:8000/asana/callback"
SCOPES = "workspaces:read projects:read custom_fields:read tasks:write"


def oauth_client() -> tuple[str, str, str]:
    client_id = setting("ASANA_CLIENT_ID", "CLIENT_ID")
    client_secret = setting("ASANA_CLIENT_SECRET", "CLIENT_SECRET")
    redirect_uri = setting("ASANA_REDIRECT_URI") or REDIRECT_URI
    if not client_id or not client_secret:
        raise AsanaError(
            "Set ASANA_CLIENT_ID and ASANA_CLIENT_SECRET in .env",
            500,
        )
    return client_id, client_secret, redirect_uri


def registered_scopes() -> str | None:
    """Registered scopes, or None when the Asana app uses Full permissions."""
    file_values = parse_env(ENV_PATH.read_text()) if ENV_PATH.exists() else {}
    if "ASANA_SCOPES" in os.environ:
        return os.environ["ASANA_SCOPES"].strip() or None
    if "ASANA_SCOPES" in file_values:
        return file_values["ASANA_SCOPES"].strip() or None
    return SCOPES
