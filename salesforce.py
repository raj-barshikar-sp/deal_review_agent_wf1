"""Read deal-review PDFs through the Salesforce REST API."""

import asyncio
import base64
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from pathlib import PurePosixPath

DOCUMENT_KINDS = (
    "purchase_order",
    "fully_executed_quote",
    "transaction_approval_form",
    "master_agreement",
)
DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloaded_docs"
ENV_PATH = Path(__file__).with_name(".env")
# Recheck this long before the noted expiry so a request does not start with a token that dies mid-download.
EXPIRY_SKEW_SECONDS = 60
_token_lock = threading.Lock()
_cached_token = ""
_cached_expiry = 0.0


def quote_id(value):
    """Validate a Salesforce quote name before it is used in SOQL."""
    value = (value or "").strip()
    if not re.fullmatch(r"[A-Za-z]+-\d+", value):
        raise ValueError("Quote ID must look like Q-12345.")
    return value


def soql_literal(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def quote_query(quote):
    return (
        "SELECT Id, SBQQ__Account__c FROM SBQQ__Quote__c "
        "WHERE Name = " + soql_literal(quote_id(quote))
    )


def agreements_query(account_id):
    return (
        "SELECT Id, Name FROM SP_Agreement_Sailpoint__c "
        "WHERE SP_Account__c = " + soql_literal(account_id)
    )


def is_agreement_name(name):
    """SP Agreements Name: End User Agreement, EULA, SLA, or SaaS Agreement."""
    normalized = normalized_title(name)
    return (
        "end user agreement" in normalized
        or "saas agreement" in normalized
        or re.search(r"(?:^| )eula(?: |$)", normalized) is not None
        or re.search(r"(?:^| )sla(?: |$)", normalized) is not None
    )


def content_links_query(entity_id):
    return (
        "SELECT ContentDocument.Title, ContentDocument.FileExtension, "
        "ContentDocument.LatestPublishedVersionId "
        "FROM ContentDocumentLink WHERE LinkedEntityId = " + soql_literal(entity_id)
    )


def normalized_title(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def matching_kinds(title):
    """Full and short names. One title may satisfy more than one kind."""
    normalized = normalized_title(title)
    kinds = []
    if "purchase order" in normalized or re.search(r"(?:^| )po(?: |$)", normalized):
        kinds.append("purchase_order")
    if "transaction approval" in normalized or re.search(r"(?:^| )taf(?: |$)", normalized):
        kinds.append("transaction_approval_form")
    if (
        "fully executed" in normalized
        or "completed" in normalized
        or re.search(r"(?:^| )fe(?: |$)", normalized)
    ):
        kinds.append("fully_executed_quote")
    return kinds


def document_kind(title):
    """First matching quote-file kind, or None."""
    kinds = matching_kinds(title)
    return kinds[0] if kinds else None


def content_document(record):
    return record.get("ContentDocument") or record.get("contentDocument") or {}


def link_document(record):
    document = content_document(record)
    return {
        "title": str(document.get("Title") or document.get("title") or ""),
        "extension": str(document.get("FileExtension") or document.get("fileExtension") or ""),
        "version_id": str(
            document.get("LatestPublishedVersionId")
            or document.get("latestPublishedVersionId")
            or ""
        ),
    }


def choose_documents(records):
    """Return candidates by kind. Two different files of one kind stay ambiguous."""
    matches = {kind: [] for kind in DOCUMENT_KINDS}
    for record in records:
        document = link_document(record)
        if not document["version_id"]:
            continue
        for kind in matching_kinds(document["title"]):
            matches[kind].append(document)
    return matches


def safe_file_name(title, extension):
    base = PurePosixPath((title or "").replace("\\", "/")).name
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" .")
    if not base:
        raise ValueError("Salesforce returned an unsafe document title.")
    extension = re.sub(r"[^A-Za-z0-9]+", "", extension or "").lower()
    if extension and not base.lower().endswith("." + extension):
        base += "." + extension
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base


def load_env():
    """Load .env without overriding variables already set in the process."""
    path = Path(__file__).with_name(".env")
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def save_pdfs(quote, documents):
    """Write each PDF into downloaded_docs next to this file."""
    folder = DOWNLOAD_DIR.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    used_names = set()
    saved = []
    for document in documents:
        name = quote + " " + safe_file_name(document["title"], document["extension"])
        stem = name[:-4]
        candidate = name
        number = 2
        while candidate.lower() in used_names:
            candidate = f"{stem} ({number}).pdf"
            number += 1
        used_names.add(candidate.lower())
        path = (folder / candidate).resolve()
        if path.parent != folder:
            raise ValueError("Refusing to write outside downloaded_docs.")
        path.write_bytes(document["data"])
        saved.append(str(path))
    return saved


def token_is_current(expires_at, now=None, skew=EXPIRY_SKEW_SECONDS):
    """True when the noted expiry is far enough ahead that a new token is unnecessary."""
    now = time.time() if now is None else now
    return expires_at > now + skew


def _instance():
    load_env()
    base_url = os.environ.get("SALESFORCE_INSTANCE_URL", "").strip().rstrip("/")
    if not base_url.startswith("https://"):
        raise RuntimeError("SALESFORCE_INSTANCE_URL must be an https URL.")
    return base_url


def _env_expiry():
    raw = os.environ.get("SALESFORCE_TOKEN_EXPIRES_AT", "").strip()
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _write_env(updates):
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    remaining = dict(updates)
    kept = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in remaining:
            kept.append(f"{key}={remaining.pop(key)}")
        else:
            kept.append(line)
    for key, value in remaining.items():
        kept.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(kept) + "\n")


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
    _write_env(updates)


def _client():
    client_id = os.environ.get("SALESFORCE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SALESFORCE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("Set SALESFORCE_CLIENT_ID and SALESFORCE_CLIENT_SECRET in .env")
    return client_id, client_secret


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _read(request):
    try:
        with urllib.request.urlopen(request, context=_ssl_context(), timeout=30) as response:
            content_type = response.headers.get_content_type()
            return response.read(), response.status, content_type
    except urllib.error.HTTPError as error:
        content_type = ""
        if error.headers is not None and hasattr(error.headers, "get_content_type"):
            content_type = error.headers.get_content_type()
        return error.read(), error.code, content_type
    except urllib.error.URLError as error:
        raise RuntimeError(f"Salesforce request failed: {error.reason}") from error


def _form_post(url, form):
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(form).encode(),
        method="POST",
    )
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("Accept", "application/json")
    raw, status, _content_type = _read(request)
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


def _introspect(token):
    client_id, client_secret = _client()
    return _form_post(
        _instance() + "/services/oauth2/introspect",
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
        print("salesforce introspect skipped: " + str(exc), flush=True)
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
    payload = _form_post(
        _instance() + "/services/oauth2/token",
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
        print("salesforce token minted", flush=True)
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


def _log(verbose, message):
    if verbose:
        print(message, flush=True)


def _get(url, verbose=False, retried=False):
    token = access_token()
    _log(verbose, "GET " + url)
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    raw, status, content_type = _read(request)
    if status == 401 and not retried:
        access_token(force=True)
        return _get(url, verbose=verbose, retried=True)
    if status >= 400:
        detail = raw.decode(errors="replace")
        _log(verbose, f"  HTTP {status} {detail}")
        raise RuntimeError(f"Salesforce REST HTTP {status}: {detail}")
    _log(verbose, f"  {status} {content_type} {len(raw)} bytes")
    return raw, content_type


def rest_query(query, verbose=False):
    """Run SOQL through /services/data/query and follow nextRecordsUrl."""
    version = os.environ.get("SALESFORCE_API_VERSION", "v66.0")
    url = _instance() + "/services/data/" + version + "/query?q=" + urllib.parse.quote(query)
    _log(verbose, "SOQL " + query)
    records = []
    while url:
        raw, _content_type = _get(url, verbose)
        body = json.loads(raw.decode())
        _log(verbose, f"  {len(body.get('records') or []) if isinstance(body, dict) else 0} records")
        if isinstance(body, list):
            message = "; ".join(
                item.get("message", str(item)) for item in body if isinstance(item, dict)
            )
            raise RuntimeError("Salesforce query failed: " + (message or str(body)))
        records.extend(body.get("records") or [])
        next_url = "" if body.get("done", True) else (body.get("nextRecordsUrl") or "")
        if not next_url:
            break
        url = next_url if next_url.startswith("https://") else _instance() + next_url
    return records


def _download_version(version_id, verbose=False):
    version = os.environ.get("SALESFORCE_API_VERSION", "v66.0")
    url = (
        _instance()
        + "/services/data/"
        + version
        + "/sobjects/ContentVersion/"
        + urllib.parse.quote(version_id, safe="")
        + "/VersionData"
    )
    data, content_type = _get(url, verbose)
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"ContentVersion {version_id} is not a PDF ({content_type}).")
    return data


async def retrieve_documents(quote, verbose=False):
    """Find the quote PDFs and save them in downloaded_docs."""
    load_env()
    quote = quote_id(quote)
    _log(verbose, "Quote " + quote)
    _log(verbose, "Directory " + str(DOWNLOAD_DIR.resolve()))
    report = {
        "status": "error",
        "quote_number": quote,
        "documents": {kind: {"status": "missing"} for kind in DOCUMENT_KINDS},
    }
    quotes = await asyncio.to_thread(rest_query, quote_query(quote), verbose)
    if not quotes:
        report["error_message"] = f"Quote {quote} was not found."
        _log(verbose, report["error_message"])
        return report
    if len(quotes) > 1:
        report["error_message"] = f"Quote {quote} matched multiple Salesforce records."
        _log(verbose, report["error_message"])
        return report
    quote_record_id = str(quotes[0].get("Id") or quotes[0].get("id") or "")
    account_id = str(quotes[0].get("SBQQ__Account__c") or "")
    if not quote_record_id:
        report["error_message"] = "Salesforce quote record has no Id."
        _log(verbose, report["error_message"])
        return report
    quote_links = await asyncio.to_thread(rest_query, content_links_query(quote_record_id), verbose)
    for record in quote_links:
        document = link_document(record)
        kinds = matching_kinds(document["title"])
        _log(verbose, f"File {document['title']!r} -> {', '.join(kinds) or 'ignored'}")
    candidates = choose_documents(quote_links)
    if account_id:
        agreements = await asyncio.to_thread(rest_query, agreements_query(account_id), verbose)
        for agreement in agreements:
            agreement_id = str(agreement.get("Id") or agreement.get("id") or "")
            agreement_name = str(agreement.get("Name") or "")
            if not agreement_id or not is_agreement_name(agreement_name):
                _log(verbose, f"Agreement skipped {agreement_name}")
                continue
            _log(verbose, f"Agreement {agreement_name}")
            linked = await asyncio.to_thread(rest_query, content_links_query(agreement_id), verbose)
            for record in linked:
                document = link_document(record)
                if document["version_id"] and document["extension"].lower() == "pdf":
                    candidates["master_agreement"].append(document)
                    _log(verbose, f"File {document['title']!r} -> master_agreement")
    else:
        _log(verbose, "Quote has no account, so no Agreement SailPoint lookup")

    selected = []
    seen_pairs = set()
    for kind in DOCUMENT_KINDS:
        matches = candidates[kind]
        if kind == "master_agreement":
            if not matches:
                _log(verbose, "Missing master_agreement")
            for document in matches:
                pair = (kind, document["version_id"])
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                _log(verbose, f"Download {kind}: {document['title']}")
                selected.append((kind, document))
            continue
        if len(matches) == 1:
            _log(verbose, f"Download {kind}: {matches[0]['title']}")
            selected.append((kind, matches[0]))
        elif len(matches) > 1:
            report["documents"][kind] = {
                "status": "ambiguous",
                "matches": [item["title"] for item in matches],
            }
            _log(verbose, f"Ambiguous {kind}: {report['documents'][kind]['matches']}")
        else:
            _log(verbose, f"Missing {kind}")
    unique = []
    seen_versions = set()
    for _, document in selected:
        if document["version_id"] in seen_versions:
            continue
        seen_versions.add(document["version_id"])
        unique.append(document)
    downloads = await asyncio.gather(
        *(asyncio.to_thread(_download_version, document["version_id"], verbose) for document in unique),
        return_exceptions=True,
    )
    by_version = {
        document["version_id"]: downloaded
        for document, downloaded in zip(unique, downloads)
    }
    ready = []
    errors = {}
    for kind, document in selected:
        downloaded = by_version[document["version_id"]]
        if isinstance(downloaded, Exception):
            errors.setdefault(kind, str(downloaded))
            _log(verbose, f"Failed {kind}: {downloaded}")
            continue
        ready.append((kind, {**document, "data": downloaded}))
    if ready:
        to_save = []
        saved_versions = set()
        for _, document in ready:
            if document["version_id"] in saved_versions:
                continue
            saved_versions.add(document["version_id"])
            to_save.append(document)
        paths = save_pdfs(quote, to_save)
        path_by_version = {
            document["version_id"]: path for document, path in zip(to_save, paths)
        }
        report["directory"] = str(DOWNLOAD_DIR.resolve())
        report["files"] = paths
        found = {kind: [] for kind in DOCUMENT_KINDS}
        for kind, document in ready:
            path = path_by_version[document["version_id"]]
            found[kind].append((document, path))
            _log(verbose, f"Saved {kind}: {path}")
        for kind, items in found.items():
            if not items:
                if kind in errors:
                    report["documents"][kind] = {"status": "error", "error_message": errors[kind]}
                continue
            if len(items) == 1:
                document, path = items[0]
                report["documents"][kind] = {
                    "status": "found",
                    "title": document["title"],
                    "path": path,
                }
            else:
                report["documents"][kind] = {
                    "status": "found",
                    "titles": [document["title"] for document, _ in items],
                    "paths": [path for _, path in items],
                }
        found_kinds = {kind for kind, items in found.items() if items}
        report["status"] = "success" if found_kinds == set(DOCUMENT_KINDS) else "partial"
        return report
    report["error_message"] = "No requested PDFs were retrieved."
    _log(verbose, report["error_message"])
    return report


def _self_check():
    assert quote_id("Q-123456") == "Q-123456"
    assert token_is_current(1_000, now=900)
    assert not token_is_current(1_000, now=950)
    assert not token_is_current(0, now=1)
    payload = base64.urlsafe_b64encode(b'{"exp":1000}').decode().rstrip("=")
    assert _jwt_expiry("x." + payload + ".y") == 1000.0
    assert _jwt_expiry("not-a-jwt") == 0.0
