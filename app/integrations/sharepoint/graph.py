"""Microsoft Graph: client-credentials token and a small JSON/bytes request helper."""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from app.core.env import setting
from app.core.http import ssl_context

GRAPH_URL = "https://graph.microsoft.com/v1.0"

_lock = threading.Lock()
_token = ""
_deadline = 0.0


class SharePointError(RuntimeError):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def site_setting() -> str:
    return setting("SHAREPOINT_SITE_URL", "SHAREPOINT_SITE")


def configured() -> bool:
    return all(setting(n) for n in ("SHAREPOINT_CLIENT_ID", "SHAREPOINT_CLIENT_SECRET")) and bool(site_setting())


def _send(request: urllib.request.Request, timeout: int = 60):
    try:
        with urllib.request.urlopen(request, context=ssl_context(), timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except urllib.error.URLError as error:
        raise SharePointError(f"SharePoint request failed: {error.reason}") from error


def tenant_id() -> str:
    """SHAREPOINT_TENANT_ID, or discovered from the site host (Microsoft publishes it unauthenticated)."""
    configured_tenant = setting("SHAREPOINT_TENANT_ID")
    if configured_tenant:
        return configured_tenant
    host = site_setting().removeprefix("https://").split("/")[0]
    if not host.endswith(".sharepoint.com"):
        raise SharePointError("Set SHAREPOINT_TENANT_ID (or a *.sharepoint.com SHAREPOINT_SITE_URL)", 500)
    domain = host.split(".")[0] + ".onmicrosoft.com"
    status, raw = _send(
        urllib.request.Request(f"https://login.microsoftonline.com/{domain}/v2.0/.well-known/openid-configuration")
    )
    try:
        issuer = json.loads(raw.decode())["issuer"]  # https://login.microsoftonline.com/<guid>/v2.0
        return issuer.split("/")[3]
    except (ValueError, KeyError, IndexError) as exc:
        raise SharePointError(f"Could not discover tenant for {domain} (HTTP {status})", 500) from exc


def access_token() -> str:
    global _token, _deadline
    with _lock:
        if _token and time.time() < _deadline:
            return _token
    tenant = tenant_id()
    client_id = setting("SHAREPOINT_CLIENT_ID")
    secret = setting("SHAREPOINT_CLIENT_SECRET")
    if not (client_id and secret):
        raise SharePointError("Set SHAREPOINT_CLIENT_ID and SHAREPOINT_CLIENT_SECRET", 500)
    form = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
            "scope": "https://graph.microsoft.com/.default",
        }
    ).encode()
    request = urllib.request.Request(
        f"https://login.microsoftonline.com/{urllib.parse.quote(tenant, safe='')}/oauth2/v2.0/token",
        data=form,
        method="POST",
    )
    status, raw = _send(request)
    body = json.loads(raw.decode() or "{}")
    if status >= 400 or not body.get("access_token"):
        raise SharePointError(
            f"Microsoft token request HTTP {status}: {body.get('error_description') or body.get('error') or ''}"[:300]
        )
    with _lock:
        _token = body["access_token"]
        _deadline = time.time() + int(body.get("expires_in") or 3600) - 120
    return _token


def request(method: str, path_or_url: str, *, json_body=None, data: bytes | None = None, headers=None):
    """Return (status, parsed JSON or None). Caller decides what a 404/409 means."""
    url = path_or_url if path_or_url.startswith("https://") else GRAPH_URL + path_or_url
    all_headers = {"Authorization": "Bearer " + access_token(), **(headers or {})}
    if json_body is not None:
        data = json.dumps(json_body).encode()
        all_headers["Content-Type"] = "application/json"
    status, raw = _send(urllib.request.Request(url, data=data, method=method, headers=all_headers))
    try:
        body = json.loads(raw.decode()) if raw else None
    except json.JSONDecodeError:
        body = None
    return status, body


def fail(label: str, status: int, body) -> SharePointError:
    detail = ""
    if isinstance(body, dict):
        error = body.get("error")
        detail = str(error.get("message") if isinstance(error, dict) else error or "")
    return SharePointError(f"{label}: HTTP {status} {detail}"[:300], 502)
