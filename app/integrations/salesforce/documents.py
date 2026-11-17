"""Classify, choose, and save the PDFs attached to a quote."""

import re
from pathlib import PurePosixPath

from app.config import DOWNLOAD_DIR

from .constants import DOCUMENT_KINDS


def normalized_title(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def is_agreement_name(name):
    """SP Agreements Name: End User Agreement, EULA, SLA, or SaaS Agreement."""
    normalized = normalized_title(name)
    return (
        "end user agreement" in normalized
        or "saas agreement" in normalized
        or re.search(r"(?:^| )eula(?: |$)", normalized) is not None
        or re.search(r"(?:^| )sla(?: |$)", normalized) is not None
    )


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
