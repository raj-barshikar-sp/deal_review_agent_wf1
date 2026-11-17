"""Print the Salesforce quote lines for one quote.

Usage: python -m scripts.fetch_quote_lines [Q-127182]
"""

import json
import os
import sys

from app.config import ENV_PATH
from app.integrations.salesforce import fetch_quote_lines
from app.integrations.salesforce.soql import quote_lines_query

DEFAULT_QUOTE = "Q-127182"


def main():
    quote = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUOTE
    if not (ENV_PATH.exists() or os.environ.get("SALESFORCE_ACCESS_TOKEN")):
        raise SystemExit("Missing " + str(ENV_PATH))
    try:
        records = fetch_quote_lines(quote)
    except RuntimeError as error:
        raise SystemExit(str(error))
    print("SOQL " + quote_lines_query(quote))
    print(json.dumps(records, indent=2))
    print("records: " + str(len(records)))


if __name__ == "__main__":
    main()
