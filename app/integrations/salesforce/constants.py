"""Salesforce integration constants."""


DOCUMENT_KINDS = (
    "purchase_order",
    "fully_executed_quote",
    "transaction_approval_form",
    "master_agreement",
)
# Recheck this long before the noted expiry so a request does not start with a token that dies mid-download.
EXPIRY_SKEW_SECONDS = 60
DEFAULT_API_VERSION = "v66.0"
