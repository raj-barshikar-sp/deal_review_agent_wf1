"""Salesforce client-credentials token cache."""

import base64
import json
import os
import threading
import time

from app.core.env import load_env, update_env_file
from app.core.log import clean, logger

from .constants import EXPIRY_SKEW_SECONDS
from .http import form_post, instance_url

_token_lock = threading.Lock()
_cached_token = ""
_cached_expiry = 0.0


def token_is_current(expires_at, now=None, skew=EXPIRY_SKEW_SECONDS):
    """True when the noted expiry is far enough ahead that a new token is unnecessary."""
    now = time.time() if now is None else now
    return expires_at > now + skew


def _env_expiry():
    raw = os.environ.get("SALESFORCE_TOKEN_EXPIRES_AT", "").strip()
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _note_token(token, expires_at, instance_url=""):
    global _cached_token, _cached_expiry
    _cached_token = token
    _cached_expiry = expires_at
    updates = {
        "SALESFORCE_ACCESS_TOKEN": token,
        "SALESFORCE_TOKEN_EXPIRES_AT": str(int(expires_at)),
    }
    if instance_url.startswith("https://"):
        updates["SALESFORCE_INSTANCE_URL"] = instance_url.rstrip("/")
    os.environ.update(updates)
    update_env_file(updates)


def _client():
    client_id = os.environ.get("SALESFORCE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SALESFORCE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("Set SALESFORCE_CLIENT_ID and SALESFORCE_CLIENT_SECRET in .env")
    return client_id, client_secret


def _introspect(token):
    client_id, client_secret = _client()
    return form_post(
        instance_url() + "/services/oauth2/introspect",
        {
            "token": token,
            "token_type_hint": "access_token",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )


def _jwt_expiry(token):
    """Read exp from our Salesforce JWT. The signature is not checked."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, json.JSONDecodeError, ValueError, TypeError):
        return 0.0
    exp = data.get("exp") if isinstance(data, dict) else None
    return float(exp) if isinstance(exp, (int, float)) and exp > 0 else 0.0


def _introspect_if_supported(token):
    try:
        return _introspect(token)
    except RuntimeError as exc:
        if "not supported" not in str(exc).lower():
            raise
        logger.info("salesforce introspect skipped: %s", clean(exc))
        return None


def _expiry_from_grant(payload):
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        return time.time() + float(expires_in)
    return 0.0


def _expiry_from_introspect(info):
    exp = info.get("exp")
    if isinstance(exp, (int, float)) and exp > 0:
        return float(exp)
    # shortcut: introspect omitted exp, recheck after 15 minutes
    return time.time() + 15 * 60


def _client_credentials():
    client_id, client_secret = _client()
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
    payload["access_token"] = token
    return payload


def access_token(force=False):
    """Reuse the current token until its noted expiry. Mint a new one only when it is not valid."""
    global _cached_token, _cached_expiry
    load_env()
    with _token_lock:
        if not _cached_token:
            _cached_token = os.environ.get("SALESFORCE_ACCESS_TOKEN", "").strip()
        if not _cached_expiry:
            _cached_expiry = _env_expiry()
        if _cached_token and not force and not token_is_current(_cached_expiry):
            _cached_expiry = _jwt_expiry(_cached_token)
        if _cached_token and not force and token_is_current(_cached_expiry):
            return _cached_token
        if _cached_token and not force:
            info = _introspect_if_supported(_cached_token) or {}
            expiry = _expiry_from_introspect(info) if info.get("active") else 0.0
            if info.get("active") and token_is_current(expiry):
                _note_token(_cached_token, expiry)
                return _cached_token
        logger.info("salesforce token minted")
        minted = _client_credentials()
        expiry = _expiry_from_grant(minted) or _jwt_expiry(minted["access_token"])
        if not expiry:
            info = _introspect_if_supported(minted["access_token"])
            expiry = _expiry_from_introspect(info) if info else time.time() + 15 * 60
        _note_token(
            minted["access_token"],
            expiry,
            str(minted.get("instance_url") or ""),
        )
        return _cached_token
