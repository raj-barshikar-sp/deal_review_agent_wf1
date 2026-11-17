"""Low-level Salesforce HTTP helpers. No authentication here."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from app.core.env import load_env
from app.core.http import ssl_context

from .constants import DEFAULT_API_VERSION


def instance_url():
    load_env()
    base_url = os.environ.get("SALESFORCE_INSTANCE_URL", "").strip().rstrip("/")
    if not base_url.startswith("https://"):
        raise RuntimeError("SALESFORCE_INSTANCE_URL must be an https URL.")
    return base_url


def read_response(request):
    try:
        with urllib.request.urlopen(request, context=ssl_context(), timeout=30) as response:
            content_type = response.headers.get_content_type()
            return response.read(), response.status, content_type
    except urllib.error.HTTPError as error:
        content_type = ""
        if error.headers is not None and hasattr(error.headers, "get_content_type"):
            content_type = error.headers.get_content_type()
        return error.read(), error.code, content_type
    except urllib.error.URLError as error:
        raise RuntimeError(f"Salesforce request failed: {error.reason}") from error


def form_post(url, form):
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(form).encode(),
        method="POST",
    )
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("Accept", "application/json")
    raw, status, _content_type = read_response(request)
    try:
        body = json.loads(raw.decode())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Salesforce auth returned HTTP {status} with a non-JSON body") from exc
    if status >= 400:
        message = ""
        if isinstance(body, dict):
            message = str(body.get("error_description") or body.get("error") or "")
        raise RuntimeError(f"Salesforce auth HTTP {status}: {message}")
    if not isinstance(body, dict):
        raise RuntimeError("Salesforce auth returned an unexpected payload")
    return body


def api_version():
    return os.environ.get("SALESFORCE_API_VERSION", DEFAULT_API_VERSION).strip() or DEFAULT_API_VERSION
