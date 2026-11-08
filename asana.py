"""Asana OAuth and Deal Review Tracker task creation."""

import base64
import hashlib
import json
import os
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Protocol

PROJECT_NAME = "TEST Deal Review Tracker"
ENV_PATH = Path(__file__).with_name(".env")
AUTHORIZE_URL = "https://app.asana.com/-/oauth_authorize"
TOKEN_URL = "https://app.asana.com/-/oauth_token"
API_URL = "https://app.asana.com/api/1.0"
REDIRECT_URI = "http://127.0.0.1:8000/asana/callback"
SCOPES = "workspaces:read projects:read custom_fields:read tasks:write"

_lock = threading.Lock()
_pending: dict[str, str] = {}
_access_token = ""
_access_deadline = 0.0


class AsanaError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


class DealTask(Protocol):
    task_name: str
    description: str
    delivery_date: date
    period: str
    quote_number: str


class CreatedTask:
    def __init__(self, gid: str, url: str):
        self.gid = gid
        self.url = url


def parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _setting(*names: str) -> str:
    file_values = parse_env(ENV_PATH.read_text()) if ENV_PATH.exists() else {}
    for name in names:
        current = os.environ.get(name, "").strip()
        if current:
            return current
        stored = file_values.get(name, "").strip()
        if stored:
            return stored
    return ""


def _client() -> tuple[str, str, str]:
    client_id = _setting("ASANA_CLIENT_ID", "CLIENT_ID")
    client_secret = _setting("ASANA_CLIENT_SECRET", "CLIENT_SECRET")
    redirect_uri = _setting("ASANA_REDIRECT_URI") or REDIRECT_URI
    if not client_id or not client_secret:
        raise AsanaError(
            "Set ASANA_CLIENT_ID and ASANA_CLIENT_SECRET in .env",
            500,
        )
    return client_id, client_secret, redirect_uri


def _save_refresh_token(token: str) -> None:
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    updated = False
    kept: list[str] = []
    for line in lines:
        if line.strip().startswith("ASANA_REFRESH_TOKEN="):
            kept.append(f"ASANA_REFRESH_TOKEN={token}")
            updated = True
        else:
            kept.append(line)
    if not updated:
        kept.append(f"ASANA_REFRESH_TOKEN={token}")
    ENV_PATH.write_text("\n".join(kept) + "\n")
    os.environ["ASANA_REFRESH_TOKEN"] = token


def _scopes() -> str | None:
    """Registered scopes, or None when the Asana app uses Full permissions."""
    file_values = parse_env(ENV_PATH.read_text()) if ENV_PATH.exists() else {}
    if "ASANA_SCOPES" in os.environ:
        return os.environ["ASANA_SCOPES"].strip() or None
    if "ASANA_SCOPES" in file_values:
        return file_values["ASANA_SCOPES"].strip() or None
    return SCOPES


def authorization_url() -> str:
    client_id, _, redirect_uri = _client()
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
    scopes = _scopes()
    if scopes:
        params["scope"] = scopes
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str, state: str) -> None:
    with _lock:
        verifier = _pending.pop(state, "")
    if not verifier:
        raise AsanaError("Asana authorization state is invalid or expired", 400)
    client_id, client_secret, redirect_uri = _client()
    payload = _token_request(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
            "code_verifier": verifier,
        }
    )
    _store_token(payload)


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
    personal = _setting("ASANA_ACCESS_TOKEN")
    if personal:
        with _lock:
            _access_token = personal
            _access_deadline = time.time() + 60 * 60 * 24
        return personal
    refresh = _setting("ASANA_REFRESH_TOKEN")
    if not refresh:
        raise AsanaError(
            "Set ASANA_ACCESS_TOKEN to a personal access token from the Asana developer console.",
            401,
        )
    client_id, client_secret, _ = _client()
    payload = _token_request(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh,
        }
    )
    return _store_token(payload)


def _store_token(payload: dict) -> str:
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


def create_task(task: DealTask) -> CreatedTask:
    project_gid = _project_gid()
    settings = _get(
        f"/projects/{project_gid}/custom_field_settings",
        {
            "opt_fields": ",".join(
                (
                    "custom_field.gid",
                    "custom_field.name",
                    "custom_field.resource_subtype",
                    "custom_field.enum_options.gid",
                    "custom_field.enum_options.name",
                    "custom_field.enum_options.enabled",
                )
            )
        },
    )["data"]
    created = _request(
        "POST",
        "/tasks",
        {"opt_fields": "gid,permalink_url"},
        {
            "data": {
                "name": task.task_name,
                "notes": task.description,
                "projects": [project_gid],
                "custom_fields": build_custom_fields(settings, task),
            }
        },
    )["data"]
    gid = str(created["gid"])
    url = str(created.get("permalink_url") or f"https://app.asana.com/0/{project_gid}/{gid}")
    return CreatedTask(gid, url)


def build_custom_fields(settings: list[dict], task: DealTask) -> dict:
    by_name: dict[str, dict] = {}
    for setting in settings:
        field = setting.get("custom_field") or setting
        name = str(field.get("name", "")).strip().lower()
        if name:
            by_name[name] = field
    values = {
        "delivery date": task.delivery_date.isoformat(),
        "period": task.period,
        "quote number": task.quote_number,
    }
    missing = [name for name in values if name not in by_name]
    if missing:
        raise AsanaError(
            f"{PROJECT_NAME} is missing custom fields: {', '.join(missing)}",
            422,
        )
    return {by_name[name]["gid"]: _field_value(by_name[name], text) for name, text in values.items()}


def _field_value(field: dict, text: str):
    subtype = field.get("resource_subtype")
    if subtype == "text":
        return text
    if subtype == "date":
        return {"date": text}
    if subtype == "enum":
        for option in field.get("enum_options") or []:
            if option.get("enabled") is False:
                continue
            if str(option.get("name", "")).strip().lower() == text.lower():
                return option["gid"]
        raise AsanaError(f"Asana field {field.get('name')} has no option {text!r}", 422)
    raise AsanaError(
        f"Asana field {field.get('name')} has unsupported type {subtype}",
        422,
    )


def _project_gid() -> str:
    matches: list[str] = []
    for workspace in _get("/workspaces", {"opt_fields": "gid,name"})["data"]:
        params = {"archived": "false", "opt_fields": "gid,name", "limit": "100"}
        while True:
            page = _get(f"/workspaces/{workspace['gid']}/projects", params)
            for project in page["data"]:
                if str(project.get("name", "")).strip() == PROJECT_NAME:
                    matches.append(str(project["gid"]))
            offset = (page.get("next_page") or {}).get("offset")
            if not offset:
                break
            params["offset"] = offset
    if not matches:
        raise AsanaError(f"Asana project {PROJECT_NAME!r} was not found", 404)
    if len(matches) > 1:
        raise AsanaError(f"More than one Asana project is named {PROJECT_NAME!r}", 409)
    return matches[0]


def _get(path: str, params: dict) -> dict:
    return _request("GET", path, params, None)


def _request(method: str, path: str, params: dict | None, payload: dict | None) -> dict:
    token = access_token()
    try:
        return _send(method, path, params, payload, token)
    except AsanaError as exc:
        if exc.status != 401:
            raise
        global _access_token, _access_deadline
        with _lock:
            _access_token = ""
            _access_deadline = 0.0
        return _send(method, path, params, payload, access_token())


def _send(method: str, path: str, params: dict | None, payload: dict | None, token: str) -> dict:
    url = API_URL + path
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    return _open(request)


def _token_request(form: dict) -> dict:
    request = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(form).encode(),
        method="POST",
    )
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("Accept", "application/json")
    try:
        return _open(request)
    except AsanaError as exc:
        if exc.status in {400, 401}:
            raise AsanaError("Asana authorization failed. Open /asana/authorize", 401) from exc
        raise


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _open(request: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=30, context=_ssl_context()) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = _error_message(exc.read())
        raise AsanaError(detail or f"Asana returned HTTP {exc.code}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise AsanaError(f"Asana request failed: {exc.reason}", 502) from exc
    if not raw:
        return {}
    return json.loads(raw)


def _error_message(raw: bytes) -> str:
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


def _self_check() -> None:
    assert parse_env('ASANA_CLIENT_ID="abc"\n# note\nASANA_CLIENT_SECRET=secret\n') == {
        "ASANA_CLIENT_ID": "abc",
        "ASANA_CLIENT_SECRET": "secret",
    }
    task = type(
        "Task",
        (),
        {
            "task_name": "Fidelity Investments",
            "description": "body",
            "delivery_date": date(2026, 11, 7),
            "period": "Nov 2026",
            "quote_number": "Q-123456",
        },
    )()
    fields = build_custom_fields(
        [
            {"custom_field": {"gid": "1", "name": "Delivery Date", "resource_subtype": "date"}},
            {"custom_field": {"gid": "2", "name": "Period", "resource_subtype": "text"}},
            {
                "custom_field": {
                    "gid": "3",
                    "name": "Quote Number",
                    "resource_subtype": "enum",
                    "enum_options": [{"gid": "opt", "name": "Q-123456", "enabled": True}],
                }
            },
        ],
        task,
    )
    assert fields == {"1": {"date": "2026-11-07"}, "2": "Nov 2026", "3": "opt"}
    try:
        build_custom_fields([], task)
    except AsanaError as exc:
        assert exc.status == 422
        return
    raise AssertionError("missing fields were accepted")
