import base64

import pytest

from app.integrations.salesforce.auth import _jwt_expiry, token_is_current
from app.integrations.salesforce.screenshot.session import (
    _jwt_audiences,
    lightning_origin,
    ret_path,
)
from app.integrations.salesforce.soql import quote_id, quote_lines_query

SANDBOX = "https://sailpoint--full.sandbox.my.salesforce.com"
DEVELOPER = "https://mydomain.develop.my.salesforce.com"


def test_quote_id():
    assert quote_id("Q-123456") == "Q-123456"
    with pytest.raises(ValueError):
        quote_id("bad id")


def test_quote_lines_query():
    query = quote_lines_query("Q-127182")
    assert "Q-127182" in query
    assert "SBQQ__QuoteLine__c" in query


def test_token_expiry():
    assert token_is_current(1_000, now=900)
    assert not token_is_current(1_000, now=950)
    assert not token_is_current(0, now=1)


def test_jwt_expiry():
    payload = base64.urlsafe_b64encode(b'{"exp":1000}').decode().rstrip("=")
    assert _jwt_expiry("x." + payload + ".y") == 1000.0
    assert _jwt_expiry("not-a-jwt") == 0.0


def test_lightning_origin_and_paths():
    assert lightning_origin(SANDBOX) == "https://sailpoint--full.sandbox.lightning.force.com"
    assert ret_path(SANDBOX + "/lightning/page/home") == "/lightning/page/home"


def test_jwt_audiences():
    assert _jwt_audiences(SANDBOX)[0] == "https://test.salesforce.com"
    assert _jwt_audiences(DEVELOPER)[0] == "https://login.salesforce.com"
    assert _jwt_audiences(DEVELOPER, explicit="https://login.salesforce.com") == [
        "https://login.salesforce.com"
    ]
    assert "https://login.salesforce.com" in _jwt_audiences(SANDBOX)
    assert _jwt_audiences(SANDBOX)[-1] == SANDBOX
