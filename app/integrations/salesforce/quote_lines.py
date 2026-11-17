"""Fetch Salesforce quote lines for one quote."""

from .client import rest_query
from .soql import quote_lines_query


def fetch_quote_lines(quote):
    """Return quote-line records for one quote."""
    return rest_query(quote_lines_query(quote))
