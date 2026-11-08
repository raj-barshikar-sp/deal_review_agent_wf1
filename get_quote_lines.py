"""Fetch Salesforce quote lines for one quote."""

import json
import os

import salesforce

QUOTE = "Q-127182"
rest_query = salesforce.rest_query
soql_literal = salesforce.soql_literal
quote_id = salesforce.quote_id


def quote_lines_query(quote):
    return (
        "SELECT Id, SBQQ__Quote__r.Name, Name, SBQQ__ProductCode__c, "
        "SBQQ__ProductName__c, SBQQ__ProductFamily__c, SBQQ__Quantity__c, "
        "SBQQ__EffectiveStartDate__c, SBQQ__EffectiveEndDate__c, "
        "CurrencyIsoCode, SBQQ__ProratedListPrice__c, "
        "convertCurrency(SBQQ__ProratedListPrice__c) ProratedListPriceConverted, "
        "SBQQ__NetPrice__c, "
        "convertCurrency(SBQQ__NetPrice__c) NetUnitPriceConverted, "
        "SBQQ__TotalDiscountRate__c, SBQQ__NetTotal__c, "
        "convertCurrency(SBQQ__NetTotal__c) NetTotalConverted "
        "FROM SBQQ__QuoteLine__c "
        "WHERE SBQQ__Quote__r.Name = " + soql_literal(quote_id(quote))
    )


def fetch_quote_lines(quote=QUOTE):
    """Return quote-line records for one quote."""
    return rest_query(quote_lines_query(quote))


def _self_check():
    query = quote_lines_query("Q-127182")
    assert "Q-127182" in query
    assert "SBQQ__QuoteLine__c" in query


def main():
    if not (salesforce.ENV_PATH.exists() or os.environ.get("SALESFORCE_ACCESS_TOKEN")):
        raise SystemExit("Missing " + str(salesforce.ENV_PATH))
    try:
        records = fetch_quote_lines(QUOTE)
    except RuntimeError as error:
        raise SystemExit(str(error))
    print("SOQL " + quote_lines_query(QUOTE))
    print(json.dumps(records, indent=2))
    print("records: " + str(len(records)))


if __name__ == "__main__":
    main()
