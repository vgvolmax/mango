import json

import pytest

requests = pytest.importorskip("requests")

from app.mango.auth import make_signature
from app.mango.client import MangoClient
from app.mango.errors import MangoApiError, MangoAuthenticationError, MangoNetworkError


class Response:
    def __init__(self, value=None, status=200): self.value, self.status_code, self.headers = value, status, {}
    def raise_for_status(self):
        if self.status_code >= 400: raise requests.HTTPError()
    def json(self):
        if isinstance(self.value, Exception): raise self.value
        return self.value


class Session:
    def __init__(self, response=None, error=None): self.response, self.error, self.sent = response, error, None
    def post(self, url, **kwargs):
        self.sent = kwargs
        if self.error: raise self.error
        return self.response


def test_client_signs_exact_json_string_sent():
    session = Session(Response({"ok": True})); MangoClient("key", "salt", session=session).post("/path", {"я": 1})
    text = session.sent["data"]["json"]
    assert text == json.dumps({"я": 1}, ensure_ascii=False, separators=(",", ":"))
    assert session.sent["data"]["sign"] == make_signature("key", text, "salt")
    assert session.sent["timeout"] == 20


@pytest.mark.parametrize("response,error", [(Response({}, 401), MangoAuthenticationError), (Response(ValueError()), MangoApiError)])
def test_client_normalizes_failures(response, error):
    with pytest.raises(error): MangoClient("key", "salt", session=Session(response)).post("/path", {})


def test_client_normalizes_timeout():
    with pytest.raises(MangoNetworkError): MangoClient("key", "salt", session=Session(error=requests.Timeout())).post("/path", {})


def test_statistics_requires_key_and_rejects_error_states():
    with pytest.raises(MangoApiError): MangoClient("key", "salt", session=Session(Response({}))).request_statistics({})
    assert MangoClient("key", "salt", session=Session(Response({"status": "work"}))).statistics_result("k")["status"] == "work"
    with pytest.raises(MangoApiError): MangoClient("key", "salt", session=Session(Response({"status": "not-found"}))).statistics_result("k")
