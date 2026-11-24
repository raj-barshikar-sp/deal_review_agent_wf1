"""Layout of the DRS "SF Quote Extract" tab and how quote-line records fill it."""

from datetime import date

SHEET = "SF Quote Extract"
HEADER_ROW = 6
FIRST_ROW = 7
LAST_COL = "W"
CORPORATE_CURRENCY = "USD"
INSTRUCTION = 'Paste quote information from Salesforce report "NDT - Quote Lines Report", extracted as Details Only.'
EXCEL_EPOCH = date(1899, 12, 30)


def _currency(record):
    return record.get("CurrencyIsoCode") or ""


def _corporate(_record):
    return CORPORATE_CURRENCY


def _field(name):
    return lambda record: record.get(name)


def _quote_name(record):
    return (record.get("SBQQ__Quote__r") or {}).get("Name") or ""


def _date(name):
    def read(record):
        value = record.get(name)
        return date.fromisoformat(value) if value else None
    return read


# (column, header, value-from-record, kind); kind drives number formats.
COLUMNS = [
    ("B", "Quote Number", _quote_name, "text"),
    ("C", "Line Name", _field("Name"), "text"),
    ("D", "Product Code", _field("SBQQ__ProductCode__c"), "text"),
    ("E", "Product Name", _field("SBQQ__ProductName__c"), "text"),
    ("F", "Product Family", _field("SBQQ__ProductFamily__c"), "text"),
    ("G", "Quantity", _field("SBQQ__Quantity__c"), "number"),
    ("H", "Effective Start Date", _date("SBQQ__EffectiveStartDate__c"), "date"),
    ("I", "Effective End Date", _date("SBQQ__EffectiveEndDate__c"), "date"),
    ("J", "Prorated List Price Currency", _currency, "text"),
    ("K", "Prorated List Price", _field("SBQQ__ProratedListPrice__c"), "money"),
    ("L", "Prorated List Price (converted) Currency", _corporate, "text"),
    ("M", "Prorated List Price (converted)", _field("ProratedListPriceConverted"), "money"),
    ("N", "Net Unit Price Currency", _currency, "text"),
    ("O", "Net Unit Price", _field("SBQQ__NetPrice__c"), "money"),
    ("P", "Net Unit Price (converted) Currency", _corporate, "text"),
    ("Q", "Net Unit Price (converted)", _field("NetUnitPriceConverted"), "money"),
    ("R", "Total Discount (%)", _field("SBQQ__TotalDiscountRate__c"), "number"),
    ("S", "Net Total Currency", _currency, "text"),
    ("T", "Net Total", _field("SBQQ__NetTotal__c"), "money"),
    ("U", "Net Total (converted) Currency", _corporate, "text"),
    ("V", "Net Total (converted)", _field("NetTotalConverted"), "money"),
    ("W", "Currency", _currency, "text"),
]


def rows(records):
    """[[(column, value, kind), ...], ...] in sheet order."""
    return [[(col, read(r), kind) for col, _, read, kind in COLUMNS] for r in records]


def excel_serial(value: date) -> int:
    return (value - EXCEL_EPOCH).days


def account_name(records) -> str:
    for record in records:
        account = ((record.get("SBQQ__Quote__r") or {}).get("SBQQ__Account__r") or {}).get("Name")
        if account:
            return account
    return ""


def order_start(records) -> date | None:
    starts = [d for d in (_date("SBQQ__EffectiveStartDate__c")(r) for r in records) if d]
    return min(starts) if starts else None
