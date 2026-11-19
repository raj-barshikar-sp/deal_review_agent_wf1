"""Turn a purchase-acknowledgement email into a task description."""

import re
from datetime import date

from app.schemas import Email, PurchaseTask

PA_SUFFIX = " - Purchase Acknowledgement for SailPoint Offerings"
QUOTE_IN_BODY = re.compile(r"\bQ-[0-9]{6}\b", re.ASCII)
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def extract_purchase(email: Email, created_on: date | None = None) -> PurchaseTask:
    subject = email.subject.strip()
    if not subject.endswith(PA_SUFFIX):
        raise ValueError(f"subject must end with {PA_SUFFIX!r}")
    task_name = subject[: -len(PA_SUFFIX)].strip()
    if not task_name:
        raise ValueError("subject has no task name")

    quotes = list(dict.fromkeys(QUOTE_IN_BODY.findall(email.body)))
    if len(quotes) != 1:
        raise ValueError("body must contain exactly one quote number matching Q-XXXXXX")

    created = created_on or date.today()
    return PurchaseTask(
        task_name=task_name,
        description=email.body,
        delivery_date=created,
        period=f"{MONTHS[created.month - 1]} {created.year}",
        quote_number=quotes[0],
    )
