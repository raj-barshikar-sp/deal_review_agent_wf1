from datetime import date

import pytest
from pydantic import ValidationError

from app.config import STATIC_DIR
from app.schemas import Email, Quote
from app.services.files import shared_file
from app.services.purchase import extract_purchase

SUFFIX = " - Purchase Acknowledgement for SailPoint Offerings"
CREATED = date(2026, 11, 7)


def test_extracts_task_fields():
    task = extract_purchase(
        Email(subject="Fidelity Investments" + SUFFIX, body="Signed quote Q-123456 is attached."),
        created_on=CREATED,
    )
    assert task.task_name == "Fidelity Investments"
    assert task.description == "Signed quote Q-123456 is attached."
    assert task.delivery_date == CREATED
    assert task.period == "Nov 2026"
    assert task.quote_number == "Q-123456"


def test_repeated_quote_number_is_one_quote():
    task = extract_purchase(
        Email(subject="Acme" + SUFFIX, body="Q-123456 then Q-123456"), created_on=CREATED
    )
    assert task.quote_number == "Q-123456"


@pytest.mark.parametrize(
    "subject, body",
    [
        ("Hello", "Quote Q-123456"),
        (SUFFIX, "Quote Q-123456"),
        ("Acme" + SUFFIX, "no quote here"),
        ("Acme" + SUFFIX, "Q-123456 and Q-654321"),
        ("Acme" + SUFFIX, "Q-1234567"),
    ],
)
def test_rejects_bad_emails(subject, body):
    with pytest.raises(ValueError):
        extract_purchase(Email(subject=subject, body=body), created_on=CREATED)


def test_shared_file_stays_inside_download_folders():
    assert shared_file("/etc/passwd") is None
    assert shared_file(str(STATIC_DIR / "index.html")) is None


def test_quote_model():
    Quote(quote_number="Q-123456")
    with pytest.raises(ValidationError):
        Quote(quote_number="Q-12")
