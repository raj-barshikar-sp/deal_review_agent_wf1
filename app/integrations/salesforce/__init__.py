"""Salesforce REST access: quote PDFs and quote lines.

The screenshot flow lives in ``salesforce.screenshot`` and is imported
explicitly, because it needs Selenium and Pillow.
"""

from .constants import DOCUMENT_KINDS
from .quote_lines import fetch_quote_lines
from .retrieval import retrieve_documents

__all__ = ["DOCUMENT_KINDS", "fetch_quote_lines", "retrieve_documents"]
