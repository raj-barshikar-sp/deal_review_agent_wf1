"""Find a quote's PDFs in Salesforce and save them to downloaded_docs."""

import asyncio

from app.config import DOWNLOAD_DIR
from app.core.env import load_env

from .auth import pdf_access_token
from .client import download_version, log, rest_query
from .constants import DOCUMENT_KINDS
from .documents import (
    choose_documents,
    is_agreement_name,
    link_document,
    matching_kinds,
    save_pdfs,
)
from .soql import agreements_query, content_links_query, quote_id, quote_query


async def retrieve_documents(quote, verbose=False):
    """Find the quote PDFs and save them in downloaded_docs."""
    load_env()
    quote = quote_id(quote)
    log(verbose, "Quote " + quote)
    log(verbose, "Directory " + str(DOWNLOAD_DIR.resolve()))
    report = {
        "status": "error",
        "quote_number": quote,
        "documents": {kind: {"status": "missing"} for kind in DOCUMENT_KINDS},
    }
    quotes = await asyncio.to_thread(rest_query, quote_query(quote), verbose, pdf_access_token)
    if not quotes:
        report["error_message"] = f"Quote {quote} was not found."
        log(verbose, report["error_message"])
        return report
    if len(quotes) > 1:
        report["error_message"] = f"Quote {quote} matched multiple Salesforce records."
        log(verbose, report["error_message"])
        return report
    quote_record_id = str(quotes[0].get("Id") or quotes[0].get("id") or "")
    account_id = str(quotes[0].get("SBQQ__Account__c") or "")
    report["account_name"] = str((quotes[0].get("SBQQ__Account__r") or {}).get("Name") or "")
    if not quote_record_id:
        report["error_message"] = "Salesforce quote record has no Id."
        log(verbose, report["error_message"])
        return report
    quote_links = await asyncio.to_thread(rest_query, content_links_query(quote_record_id), verbose, pdf_access_token)
    for record in quote_links:
        document = link_document(record)
        kinds = matching_kinds(document["title"])
        log(verbose, f"File {document['title']!r} -> {', '.join(kinds) or 'ignored'}")
    candidates = choose_documents(quote_links)
    if account_id:
        agreements = await asyncio.to_thread(rest_query, agreements_query(account_id), verbose, pdf_access_token)
        for agreement in agreements:
            agreement_id = str(agreement.get("Id") or agreement.get("id") or "")
            agreement_name = str(agreement.get("Name") or "")
            if not agreement_id or not is_agreement_name(agreement_name):
                log(verbose, f"Agreement skipped {agreement_name}")
                continue
            log(verbose, f"Agreement {agreement_name}")
            linked = await asyncio.to_thread(rest_query, content_links_query(agreement_id), verbose, pdf_access_token)
            for record in linked:
                document = link_document(record)
                if document["version_id"] and document["extension"].lower() == "pdf":
                    candidates["master_agreement"].append(document)
                    log(verbose, f"File {document['title']!r} -> master_agreement")
    else:
        log(verbose, "Quote has no account, so no Agreement SailPoint lookup")

    selected = []
    seen_pairs = set()
    for kind in DOCUMENT_KINDS:
        matches = candidates[kind]
        if kind == "master_agreement":
            if not matches:
                log(verbose, "Missing master_agreement")
            for document in matches:
                pair = (kind, document["version_id"])
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                log(verbose, f"Download {kind}: {document['title']}")
                selected.append((kind, document))
            continue
        if len(matches) == 1:
            log(verbose, f"Download {kind}: {matches[0]['title']}")
            selected.append((kind, matches[0]))
        elif len(matches) > 1:
            report["documents"][kind] = {
                "status": "ambiguous",
                "matches": [item["title"] for item in matches],
            }
            log(verbose, f"Ambiguous {kind}: {report['documents'][kind]['matches']}")
        else:
            log(verbose, f"Missing {kind}")
    unique = []
    seen_versions = set()
    for _, document in selected:
        if document["version_id"] in seen_versions:
            continue
        seen_versions.add(document["version_id"])
        unique.append(document)
    downloads = await asyncio.gather(
        *(asyncio.to_thread(download_version, document["version_id"], verbose, pdf_access_token) for document in unique),
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
            log(verbose, f"Failed {kind}: {downloaded}")
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
            log(verbose, f"Saved {kind}: {path}")
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
    log(verbose, report["error_message"])
    return report
