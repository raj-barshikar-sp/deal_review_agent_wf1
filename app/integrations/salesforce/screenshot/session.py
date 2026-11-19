"""Mint a web-scoped JWT-bearer token and build the frontdoor login URL."""

import os
import time
import urllib.parse
from pathlib import Path

from app.config import DEFAULT_JWT_KEY_FILE
from app.core.env import load_env

from ..http import form_post


def lightning_origin(instance):
    """Lightning host for the org that issued the access token.

    https://sailpoint--full.sandbox.my.salesforce.com
    becomes https://sailpoint--full.sandbox.lightning.force.com
    """
    parts = urllib.parse.urlsplit(instance)
    host = parts.netloc
    suffix = ".my.salesforce.com"
    if host.endswith(suffix):
        host = host[: -len(suffix)] + ".lightning.force.com"
    return "https://" + host


def _jwt_audiences(domain, explicit=""):
    """Hosts Salesforce accepts as the JWT audience. Sandboxes use test.salesforce.com."""
    if explicit:
        return [explicit]
    host = urllib.parse.urlsplit(domain).netloc
    first = "https://test.salesforce.com" if ".sandbox." in host else "https://login.salesforce.com"
    audiences = []
    for item in (first, "https://login.salesforce.com", "https://test.salesforce.com", domain.rstrip("/")):
        if item not in audiences:
            audiences.append(item)
    return audiences


def _private_key():
    pem = os.environ.get("SALESFORCE_JWT_PRIVATE_KEY", "").strip()
    if pem:
        return pem.replace("\\n", "\n")
    key_file = Path(os.environ.get("SALESFORCE_JWT_KEY_FILE", "").strip() or DEFAULT_JWT_KEY_FILE)
    if key_file.is_file():
        return key_file.read_text()
    return ""


def _screenshot_login():
    """My Domain, consumer key, integration username, and the JWT private key."""
    load_env()
    domain = os.environ.get("SALESFORCE_INSTANCE_URL", "").strip().rstrip("/")
    client_id = (
        os.environ.get("SF_PROD_ID", "").strip()
        or os.environ.get("SALESFORCE_JWT_CLIENT_ID", "").strip()
        or os.environ.get("SALESFORCE_CLIENT_ID", "").strip()
    )
    username = os.environ.get("SALESFORCE_USERNAME", "").strip()
    key = _private_key()
    missing = []
    if not domain.startswith("https://"):
        missing.append("SALESFORCE_INSTANCE_URL")
    if not client_id:
        missing.append("SF_PROD_ID")
    if not username:
        missing.append("SALESFORCE_USERNAME")
    if not key:
        missing.append("SALESFORCE_JWT_PRIVATE_KEY, SALESFORCE_JWT_KEY_FILE, or certs/sf-jwt.key")
    if missing:
        raise RuntimeError("Screenshot login is missing " + ", ".join(missing) + ".")
    return domain, client_id, username, key


def web_token():
    """Mint a web-scoped token for the integration user. Client credentials cannot open frontdoor."""
    domain, client_id, username, private_key = _screenshot_login()
    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError("Install PyJWT[crypto] to sign the Salesforce screenshot login.") from exc
    explicit = os.environ.get("SALESFORCE_JWT_AUDIENCE", "").strip()
    last_error = ""
    for audience in _jwt_audiences(domain, explicit):
        assertion = jwt.encode(
            {"iss": client_id, "sub": username, "aud": audience, "exp": int(time.time()) + 180},
            private_key,
            algorithm="RS256",
        )
        try:
            body = form_post(
                domain + "/services/oauth2/token",
                {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
            )
            break
        except RuntimeError as exc:
            last_error = str(exc)
            if "invalid assertion" not in last_error.lower() and "audience" not in last_error.lower():
                raise
    else:
        raise RuntimeError(
            "Salesforce rejected the screenshot JWT (" + last_error + "). "
            "Check the uploaded certificate, the Consumer Key, and that SALESFORCE_USERNAME "
            "is exactly the integration user's username."
        )
    token = str(body.get("access_token") or "")
    if not token:
        raise RuntimeError("Salesforce token response did not include an access token.")
    return token, str(body.get("instance_url") or domain).rstrip("/")


def ret_path(page_url):
    """Path Salesforce should open after frontdoor accepts the access token."""
    parts = urllib.parse.urlsplit(page_url)
    if not parts.path:
        return "/lightning/page/home"
    return parts.path + (("?" + parts.query) if parts.query else "")


def frontdoor_url(instance, token, ret_url):
    """Log in on the org that issued the token, then open ret_url."""
    return instance.rstrip("/") + "/secur/frontdoor.jsp?" + urllib.parse.urlencode({
        "sid": token,
        "retURL": ret_url,
    })
