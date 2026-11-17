"""Asana HTTP transport and error mapping."""

import json
import urllib.error
import urllib.parse
import urllib.request

from app.core.http import ssl_context

from .errors import AsanaError
from .settings import API_URL, TOKEN_URL


def send(method: str, path: str, params: dict | None, payload: dict | None, token: str) -> dict:
    url = API_URL + path
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    return open_request(request)


def token_request(form: dict) -> dict:
    request = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(form).encode(),
        method="POST",
    )
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("Accept", "application/json")
    try:
        return open_request(request)
    except AsanaError as exc:
        if exc.status in {400, 401}:
            raise AsanaError("Asana authorization failed. Open /asana/authorize", 401) from exc
        raise


def open_request(request: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=30, context=ssl_context()) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = error_message(exc.read())
        raise AsanaError(detail or f"Asana returned HTTP {exc.code}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise AsanaError(f"Asana request failed: {exc.reason}", 502) from exc
    if not raw:
        return {}
    return json.loads(raw)


def error_message(raw: bytes) -> str:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if isinstance(errors, list) and errors:
        message = errors[0].get("message")
        if isinstance(message, str):
            return message
    if isinstance(payload, dict):
        message = payload.get("error_description") or payload.get("error")
        if isinstance(message, str):
            return message
    return ""
