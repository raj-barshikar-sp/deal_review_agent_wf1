from datetime import date

import pytest

from app.integrations.sharepoint import drs_name, folder_segments, month_folder
from app.integrations.sharepoint.layout import clean_name


def test_month_folder():
    assert month_folder(date(2026, 4, 7)) == "2026.04 April"


def test_folder_segments():
    assert folder_segments("Order Processing/2024 Invoices", "Acme: Corp.", date(2026, 4, 7)) == [
        "Order Processing", "2024 Invoices", "Acme Corp", "New Deals", "2026.04 April",
    ]


def test_drs_name():
    assert drs_name(date(2026, 4, 7), "Fidelity Investments", date(2026, 3, 1)) == (
        "DRS - 4.07.2026 - Fidelity Investments (03.2026).xlsx"
    )


def test_clean_name_rejects_empty():
    with pytest.raises(ValueError):
        clean_name(" ../ ")
