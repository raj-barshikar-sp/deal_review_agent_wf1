"""Authenticated Salesforce REST calls: SOQL queries and file downloads."""

import json
import urllib.parse
import urllib.request

from app.core.log import clean, logger

from .auth import access_token
from .http import api_version, instance_url, read_response


def log(verbose, message):
    if verbose:
        logger.debug(clean(message, 1000))


def get(url, verbose=False, retried=False):
    token = access_token()
    log(verbose, "GET " + url)
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    raw, status, content_type = read_response(request)
    if status == 401 and not retried:
        access_token(force=True)
        return get(url, verbose=verbose, retried=True)
    if status >= 400:
        detail = raw.decode(errors="replace")
        log(verbose, f"  HTTP {status} {detail}")
        logger.error("Salesforce REST HTTP %s: %s", status, clean(detail, 1000))
        raise RuntimeError(f"Salesforce REST HTTP {status}")
    log(verbose, f"  {status} {content_type} {len(raw)} bytes")
    return raw, content_type


def rest_query(query, verbose=False):
    """Run SOQL through /services/data/query and follow nextRecordsUrl."""
    url = instance_url() + "/services/data/" + api_version() + "/query?q=" + urllib.parse.quote(query)
    log(verbose, "SOQL " + query)
    records = []
    while url:
        raw, _content_type = get(url, verbose)
        body = json.loads(raw.decode())
        log(verbose, f"  {len(body.get('records') or []) if isinstance(body, dict) else 0} records")
        if isinstance(body, list):
            message = "; ".join(
                item.get("message", str(item)) for item in body if isinstance(item, dict)
            )
            logger.error("Salesforce query failed: %s", clean(message or body, 1000))
            raise RuntimeError("Salesforce query failed")
        records.extend(body.get("records") or [])
        next_url = "" if body.get("done", True) else (body.get("nextRecordsUrl") or "")
        if not next_url:
            break
        url = next_url if next_url.startswith("https://") else instance_url() + next_url
    return records


def download_version(version_id, verbose=False):
    url = (
        instance_url()
        + "/services/data/"
        + api_version()
        + "/sobjects/ContentVersion/"
        + urllib.parse.quote(version_id, safe="")
        + "/VersionData"
    )
    data, content_type = get(url, verbose)
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"ContentVersion {version_id} is not a PDF ({content_type}).")
    return data
