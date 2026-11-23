"""Salesforce client-credentials tokens. Nothing is cached: every call mints a new token."""

import os

from app.core.env import load_env
from app.core.log import logger

from .http import form_post, instance_url


def _client():
    client_id = (os.environ.get("SF_PROD_ID") or os.environ.get("SALESFORCE_CLIENT_ID", "")).strip()
    client_secret = (
        os.environ.get("SF_PROD_SECRET") or os.environ.get("SALESFORCE_CLIENT_SECRET", "")
    ).strip()
    if not client_id or not client_secret:
        raise RuntimeError("Set SF_PROD_ID and SF_PROD_SECRET in .env")
    return client_id, client_secret


def _mint(client_id, client_secret):
    payload = form_post(
        instance_url() + "/services/oauth2/token",
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    token = str(payload.get("access_token") or "")
    if not token:
        raise RuntimeError("Salesforce token response did not include an access token")
    return token


def pdf_access_token(force=False):
    """TEMPORARY: token for PDF retrieval, minted with SALESFORCE_CLIENT_ID/SECRET."""
    load_env()
    client_id = os.environ.get("SALESFORCE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SALESFORCE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("Set SALESFORCE_CLIENT_ID and SALESFORCE_CLIENT_SECRET in .env")
    logger.info("salesforce pdf token minted")
    return _mint(client_id, client_secret)


def access_token(force=False):
    """Mint a fresh token on every call (`force` is accepted for compatibility)."""
    load_env()
    logger.info("salesforce token minted")
    return _mint(*_client())
