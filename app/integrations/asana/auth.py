"""Asana OAuth (PKCE) and bearer-token caching."""

import base64
import hashlib
import os
import secrets
import threading
import time
import urllib.parse

from app.core.env import update_env_file

from .errors import AsanaError
from .http import token_request
from .settings import AUTHORIZE_URL, oauth_client, registered_scopes, setting

_lock = threading.Lock()
_pending: dict[str, str] = {}
_access_token = ""
_access_deadline = 0.0


def _save_refresh_token(token: str) -> None:
    update_env_file({"ASANA_REFRESH_TOKEN": token})
    os.environ["ASANA_REFRESH_TOKEN"] = token


def authorization_url() -> str:
    client_id, _, redirect_uri = oauth_client()
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode().rstrip("=")
    with _lock:
        _pending[state] = verifier
        if len(_pending) > 20:
            _pending.pop(next(iter(_pending)))
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    scopes = registered_scopes()
    if scopes:
        params["scope"] = scopes
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str, state: str) -> None:
    with _lock:
        verifier = _pending.pop(state, "")
    if not verifier:
        raise AsanaError("Asana authorization state is invalid or expired", 400)
    client_id, client_secret, redirect_uri = oauth_client()
    payload = token_request(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
            "code_verifier": verifier,
        }
    )
    store_token(payload)


def access_token() -> str:
    """Bearer token for Asana API calls.

    A personal access token in ASANA_ACCESS_TOKEN is used as-is. That is the
    same path that created tasks in Test_Deal_Review, and it does not install
    the OAuth app. A refresh token is only used when no personal token is set.
    """
    global _access_token, _access_deadline
    with _lock:
        if _access_token and time.time() < _access_deadline:
            return _access_token
    personal = setting("ASANA_ACCESS_TOKEN")
    if personal:
        with _lock:
            _access_token = personal
            _access_deadline = time.time() + 60 * 60 * 24
        return personal
    refresh = setting("ASANA_REFRESH_TOKEN")
    if not refresh:
        raise AsanaError(
            "Set ASANA_ACCESS_TOKEN to a personal access token from the Asana developer console.",
            401,
        )
    client_id, client_secret, _ = oauth_client()
    payload = token_request(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh,
        }
    )
    return store_token(payload)


def store_token(payload: dict) -> str:
    global _access_token, _access_deadline
    token = str(payload.get("access_token") or "")
    if not token:
        raise AsanaError("Asana token response did not include an access token", 502)
    expires_in = int(payload.get("expires_in") or 3600)
    with _lock:
        _access_token = token
        _access_deadline = time.time() + expires_in - 60
    refresh = payload.get("refresh_token")
    if isinstance(refresh, str) and refresh:
        _save_refresh_token(refresh)
    return token


def invalidate_token() -> None:
    """Forget the cached bearer token so the next call fetches a fresh one."""
    global _access_token, _access_deadline
    with _lock:
        _access_token = ""
        _access_deadline = 0.0
