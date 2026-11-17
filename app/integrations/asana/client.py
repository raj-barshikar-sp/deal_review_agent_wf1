"""Authenticated Asana API requests."""

from . import auth
from .errors import AsanaError
from .http import send


def get(path: str, params: dict) -> dict:
    return request("GET", path, params, None)


def request(method: str, path: str, params: dict | None, payload: dict | None) -> dict:
    try:
        return send(method, path, params, payload, auth.access_token())
    except AsanaError as exc:
        if exc.status != 401:
            raise
        auth.invalidate_token()
        return send(method, path, params, payload, auth.access_token())
