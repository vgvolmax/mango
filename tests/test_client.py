import json

import pytest

requests = pytest.importorskip("requests")

from app.mango.auth import make_signature
from app.mango.client import MangoClient
from app.mango.errors import MangoApiError, MangoAuthenticationError, MangoNetworkError


class Response:
    def __init__(self, value=None, status=200): self.value, self.status_code, self.headers, self.closed = value, status, {}, False
    def raise_for_status(self):
        if self.status_code >= 400: raise requests.HTTPError()
    def json(self):
        if isinstance(self.value, Exception): raise self.value
        return self.value
    def close(self): self.closed = True


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


@pytest.mark.parametrize("value", [
    {"result": 1000},
    {"status": "work"},
    {"status": "complete"},
])
def test_client_accepts_numeric_success_and_active_async_statuses(value):
    assert MangoClient("key", "salt", session=Session(Response(value))).post("/path", {}) == value


@pytest.mark.parametrize("value", [{"result": 5000}, {"status": "error"}])
def test_client_rejects_numeric_and_async_errors(value):
    with pytest.raises(MangoApiError):
        MangoClient("key", "salt", session=Session(Response(value))).post("/path", {})


def test_check_credentials_rejects_numeric_api_error():
    with pytest.raises(MangoApiError):
        MangoClient("key", "salt", session=Session(Response({"result": 5000}))).check_credentials()

class RecordingResponse(Response):
    def __init__(self, value=None, status=200, headers=None, error_url=None):
        super().__init__(value, status)
        self.headers = headers or {}
        self.error_url = error_url
        self.closed = False

    def raise_for_status(self):
        if self.error_url:
            raise requests.HTTPError(f"403 Client Error for url: {self.error_url}")
        super().raise_for_status()

    def close(self):
        self.closed = True


class RecordingSession(Session):
    def __init__(self, redirects, audio=None, get_error=None):
        self.redirects = iter(redirects)
        self.audio = audio
        self.get_error = get_error
        self.post_calls = 0
        self.get_urls = []

    def post(self, url, **kwargs):
        self.post_calls += 1
        return next(self.redirects)

    def get(self, url, **kwargs):
        self.get_urls.append(url)
        if self.get_error:
            raise self.get_error
        return self.audio


def test_open_recording_closes_redirect_and_audio():
    redirect = RecordingResponse(status=302, headers={"Location": "temporary"})
    audio = RecordingResponse(headers={"Content-Type": "audio/mpeg"})
    session = RecordingSession([redirect], audio)

    with MangoClient("key", "salt", session=session).open_recording("recording") as response:
        assert response is audio
        assert redirect.closed
        assert not audio.closed

    assert audio.closed
    assert session.get_urls == ["temporary"]


@pytest.mark.parametrize("status,headers", [(200, {"Location": "temporary"}), (302, {})])
def test_open_recording_closes_invalid_redirect(status, headers):
    redirect = RecordingResponse(status=status, headers=headers)
    client = MangoClient("key", "salt", session=RecordingSession([redirect]))

    with pytest.raises(MangoApiError):
        with client.open_recording("recording"):
            pass

    assert redirect.closed


def test_open_recording_sanitizes_get_http_error_and_traceback():
    import traceback

    secret_url = "https://files.mango-office.ru/SECRET_ONE_TIME_TOKEN"
    redirect = RecordingResponse(status=302, headers={"Location": secret_url})
    audio = RecordingResponse(status=403, error_url=secret_url)
    client = MangoClient("key", "salt", session=RecordingSession([redirect], audio))

    with pytest.raises(MangoNetworkError) as captured:
        with client.open_recording("recording"):
            pass

    formatted = "".join(traceback.format_exception(captured.type, captured.value, captured.tb))
    assert secret_url not in str(captured.value)
    assert secret_url not in formatted
    assert "files.mango-office.ru" not in formatted
    assert redirect.closed and audio.closed


def test_open_recording_sanitizes_consumer_stream_error_and_closes():
    secret_url = "https://files.mango-office.ru/SECRET_STREAM_TOKEN"
    redirect = RecordingResponse(status=302, headers={"Location": secret_url})
    audio = RecordingResponse()
    client = MangoClient("key", "salt", session=RecordingSession([redirect], audio))

    with pytest.raises(MangoNetworkError) as captured:
        with client.open_recording("recording"):
            raise requests.ConnectionError(f"stream failed for {secret_url}")

    assert str(captured.value) == "Recording download failed"
    assert captured.value.__cause__ is None
    assert captured.value.__suppress_context__
    assert audio.closed


def test_open_recording_sanitizes_get_connection_error():
    secret_url = "https://files.mango-office.ru/SECRET_GET_TOKEN"
    redirect = RecordingResponse(status=302, headers={"Location": secret_url})
    session = RecordingSession([redirect], get_error=requests.ConnectionError(secret_url))

    with pytest.raises(MangoNetworkError) as captured:
        with MangoClient("key", "salt", session=session).open_recording("recording"):
            pass

    assert secret_url not in str(captured.value)
    assert redirect.closed
