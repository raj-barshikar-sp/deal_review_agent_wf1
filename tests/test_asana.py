from datetime import date

import pytest

from app.core.env import parse_env
from app.integrations.asana import AsanaError
from app.integrations.asana.tasks import build_custom_fields


def make_task():
    return type(
        "Task",
        (),
        {
            "task_name": "Fidelity Investments",
            "description": "body",
            "delivery_date": date(2026, 11, 7),
            "period": "Nov 2026",
            "quote_number": "Q-123456",
        },
    )()


def test_parse_env():
    assert parse_env('ASANA_CLIENT_ID="abc"\n# note\nASANA_CLIENT_SECRET=secret\n') == {
        "ASANA_CLIENT_ID": "abc",
        "ASANA_CLIENT_SECRET": "secret",
    }


def test_build_custom_fields():
    fields = build_custom_fields(
        [
            {"custom_field": {"gid": "1", "name": "Delivery Date", "resource_subtype": "date"}},
            {"custom_field": {"gid": "2", "name": "Period", "resource_subtype": "text"}},
            {
                "custom_field": {
                    "gid": "3",
                    "name": "Quote Number",
                    "resource_subtype": "enum",
                    "enum_options": [{"gid": "opt", "name": "Q-123456", "enabled": True}],
                }
            },
        ],
        make_task(),
    )
    assert fields == {"1": {"date": "2026-11-07"}, "2": "Nov 2026", "3": "opt"}


def test_missing_custom_fields_are_rejected():
    with pytest.raises(AsanaError) as info:
        build_custom_fields([], make_task())
    assert info.value.status == 422
