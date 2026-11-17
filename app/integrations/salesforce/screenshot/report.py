"""Locate the Quote Lines report and build its page URL."""

import json
import os
import urllib.parse
import urllib.request

from ..http import api_version, read_response
from ..soql import soql_literal
from .session import lightning_origin

REPORT_DEVELOPER_NAME = "Quote_Lines"


def _query(instance, token, soql):
    url = instance + "/services/data/" + api_version() + "/query?q=" + urllib.parse.quote(soql)
    request = urllib.request.Request(
        url,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    raw, status, _content_type = read_response(request)
    if status >= 400:
        raise RuntimeError(f"Salesforce report lookup failed ({status}): {raw.decode(errors='replace')[:300]}")
    body = json.loads(raw.decode())
    if isinstance(body, list):
        message = "; ".join(item.get("message", str(item)) for item in body if isinstance(item, dict))
        raise RuntimeError("Salesforce report lookup failed: " + (message or str(body)))
    return body.get("records") or []


def _report_id(instance, token, field, value):
    rows = _query(
        instance,
        token,
        "SELECT Id FROM Report WHERE " + field + " = " + soql_literal(value) + " LIMIT 2",
    )
    if len(rows) != 1:
        raise RuntimeError(f"Expected one Salesforce report with {field} {value!r}, found {len(rows)}.")
    report_id = str(rows[0].get("Id") or rows[0].get("id") or "")
    if not report_id:
        raise RuntimeError(f"Salesforce report {value!r} has no Id.")
    return report_id


def report_page_url(quote, instance, token):
    """Report page for this quote. fv0 applies only when Quote Number is the report's first filter."""
    origin = lightning_origin(instance)
    explicit = os.environ.get("SALESFORCE_SCREENSHOT_URL", "").strip()
    if explicit:
        url = explicit.format(quote=urllib.parse.quote(quote))
        return url, "/lightning/r/Report/" in url
    report_id = os.environ.get("SALESFORCE_QUOTE_LINES_REPORT_ID", "").strip()
    if not report_id:
        name = os.environ.get("SALESFORCE_QUOTE_LINES_REPORT_NAME", "").strip()
        if name:
            report_id = _report_id(instance, token, "Name", name)
        else:
            report_id = _report_id(instance, token, "DeveloperName", REPORT_DEVELOPER_NAME)
    url = (
        origin
        + "/lightning/r/Report/"
        + urllib.parse.quote(report_id, safe="")
        + "/view?fv0="
        + urllib.parse.quote(quote)
    )
    return url, True
