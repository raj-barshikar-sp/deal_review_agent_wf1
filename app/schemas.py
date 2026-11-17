"""Request and response models."""

import re
from datetime import date

from pydantic import BaseModel, field_validator

QUOTE_EXACT = re.compile(r"^Q-\d{6}$")


class Email(BaseModel):
    subject: str
    body: str

    @field_validator("subject", "body")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be non-empty text")
        return value


class PurchaseTask(BaseModel):
    task_name: str
    description: str
    delivery_date: date
    period: str
    quote_number: str


class CreatedPurchaseTask(PurchaseTask):
    asana_gid: str
    asana_url: str
    documents: dict


class Quote(BaseModel):
    quote_number: str

    @field_validator("quote_number")
    @classmethod
    def matches(cls, value: str) -> str:
        if QUOTE_EXACT.fullmatch(value) is None:
            raise ValueError("must match Q-XXXXXX")
        return value


class QuoteLinesResult(BaseModel):
    quote_number: str
    record_count: int
    records: list
    screenshot_taken_at: str
    screenshot_path: str
    page_url: str
