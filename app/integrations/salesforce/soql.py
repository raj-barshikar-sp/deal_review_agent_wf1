"""SOQL builders and input validation."""

import re


def quote_id(value):
    """Validate a Salesforce quote name before it is used in SOQL."""
    value = (value or "").strip()
    if not re.fullmatch(r"[A-Za-z]+-[0-9]+", value):
        raise ValueError("Quote ID must look like Q-12345.")
    return value


def soql_literal(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def quote_query(quote):
    return (
        "SELECT Id, SBQQ__Account__c, SBQQ__Account__r.Name FROM SBQQ__Quote__c "
        "WHERE Name = " + soql_literal(quote_id(quote))
    )


def agreements_query(account_id):
    return (
        "SELECT Id, Name FROM SP_Agreement_Sailpoint__c "
        "WHERE SP_Account__c = " + soql_literal(account_id)
    )


def content_links_query(entity_id):
    return (
        "SELECT ContentDocument.Title, ContentDocument.FileExtension, "
        "ContentDocument.LatestPublishedVersionId "
        "FROM ContentDocumentLink WHERE LinkedEntityId = " + soql_literal(entity_id)
    )


def quote_lines_query(quote):
    return (
        "SELECT Id, SBQQ__Quote__r.Name, SBQQ__Quote__r.SBQQ__Account__r.Name, Name, SBQQ__ProductCode__c, "
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
