from contextlib import contextmanager
from datetime import datetime, timezone

import requests

from app.core.logging_setup import configure_logging
from app.mango.client import MangoClient
from app.mango.errors import MangoNetworkError
from app.mango.models import CallDirection, CallRecord
from app.services.downloads import DownloadHistory, DownloadService, safe_filename


class Response:
    def __init__(self, chunks=(b"mp3",), content_type="audio/mpeg"):
        self.headers = {"Content-Type": content_type} if content_type is not None else {}
        self.chunks = chunks
        self.closed = False

    def iter_content(self, _):
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def close(self):
        self.closed = True


class Client:
    def __init__(self, responses=None):
        self.responses = iter(responses or [RuntimeError("expired"), Response()])
        self.attempts = 0

    @contextmanager
    def open_recording(self, _recording_id):
        self.attempts += 1
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        try:
            yield value
        except requests.RequestException:
            raise MangoNetworkError("Recording download failed") from None
        finally:
            value.close()


def call(recording_id="r"):
    return CallRecord("e", CallDirection.INCOMING, datetime(2026, 8, 11, tzinfo=timezone.utc), "7999", None, ("Иванов / Отдел",), 1, 1, (recording_id,))


def test_download_retries_with_fresh_url_then_skips_history(tmp_path):
    first_url = "https://files.mango-office.ru/SECRET_URL_1"
    second_url = "https://files.mango-office.ru/SECRET_URL_2"
    response = Response()
    client = Client([requests.ConnectionError(first_url), response])
    history_path = tmp_path / "history.json"
    service = DownloadService(client, DownloadHistory(history_path))

    result = service.download([call()], tmp_path / "audio")

    assert result.downloaded == 1 and client.attempts == 2
    assert response.closed
    assert not list(tmp_path.rglob("*.part"))
    history_text = history_path.read_text(encoding="utf-8")
    assert first_url not in history_text and second_url not in history_text
    assert service.download([call()], tmp_path / "audio").skipped == 1


def test_deleted_history_file_is_downloaded_again(tmp_path):
    service = DownloadService(Client([RuntimeError("expired"), Response(), Response()]), DownloadHistory(tmp_path / "history.json"))
    service.download([call()], tmp_path / "audio")
    next((tmp_path / "audio").glob("*.mp3")).unlink()
    assert service.download([call()], tmp_path / "audio").downloaded == 1


def test_windows_safe_filename():
    value = safe_filename('<>:"/\\|?* Петров: тест? Иванов / Отдел ' + "я" * 300)
    assert not any(char in value for char in '<>:"/\\|?*')
    assert len(value) <= 180 and "Петров" in value


def test_bad_content_type_closes_each_response_and_leaves_no_files(tmp_path):
    responses = [Response(content_type="text/html"), Response(content_type="text/html")]
    result = DownloadService(Client(responses), DownloadHistory(tmp_path / "history.json")).download([call()], tmp_path / "audio")

    assert result.errors == 1
    assert all(response.closed for response in responses)
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("*.mp3"))


def test_empty_recording_closes_response_and_removes_part(tmp_path):
    responses = [Response(chunks=()), Response(chunks=())]
    result = DownloadService(Client(responses), DownloadHistory(tmp_path / "history.json")).download([call()], tmp_path / "audio")

    assert result.errors == 1
    assert all(response.closed for response in responses)
    assert not list(tmp_path.rglob("*.part"))


def test_stream_failure_closes_responses_removes_part_and_retries(tmp_path):
    secret = "https://files.mango-office.ru/SECRET_STREAM_TOKEN"
    responses = [Response((b"partial", requests.ConnectionError(secret))), Response((b"complete",))]
    client = Client(responses)

    result = DownloadService(client, DownloadHistory(tmp_path / "history.json")).download([call()], tmp_path / "audio")

    assert result.downloaded == 1 and client.attempts == 2
    assert all(response.closed for response in responses)
    assert not list(tmp_path.rglob("*.part"))
    assert next((tmp_path / "audio").glob("*.mp3")).read_bytes() == b"complete"


def test_retry_requests_a_fresh_location_from_mango(tmp_path):
    urls = [
        "https://files.mango-office.ru/SECRET_URL_1",
        "https://files.mango-office.ru/SECRET_URL_2",
    ]

    class HttpResponse(Response):
        def __init__(self, *, status=200, location=None, chunks=(b"mp3",)):
            super().__init__(chunks)
            self.status_code = status
            if location:
                self.headers = {"Location": location}

        def raise_for_status(self):
            return None

    redirects = [HttpResponse(status=302, location=url) for url in urls]
    audios = [HttpResponse(chunks=(b"partial", requests.ConnectionError(urls[0]))), HttpResponse()]

    class Session:
        def __init__(self):
            self.post_calls = 0
            self.get_urls = []

        def post(self, _url, **_kwargs):
            response = redirects[self.post_calls]
            self.post_calls += 1
            return response

        def get(self, url, **_kwargs):
            self.get_urls.append(url)
            return audios[len(self.get_urls) - 1]

    session = Session()
    history_path = tmp_path / "history.json"
    service = DownloadService(MangoClient("key", "salt", session=session), DownloadHistory(history_path))

    result = service.download([call()], tmp_path / "audio")

    assert result.downloaded == 1
    assert session.post_calls == 2
    assert session.get_urls == urls
    assert all(response.closed for response in redirects + audios)
    history_text = history_path.read_text(encoding="utf-8")
    assert all(url not in history_text for url in urls)


def test_secret_url_is_absent_from_application_log(tmp_path):
    secret = "https://files.mango-office.ru/SECRET_LOG_TOKEN"
    log_file = tmp_path / "logs" / "app.log"
    configure_logging(log_file)

    class HttpResponse:
        status_code = 302
        headers = {"Location": secret}

        def close(self):
            pass

    class Session:
        def post(self, _url, **_kwargs):
            return HttpResponse()

        def get(self, url, **_kwargs):
            raise requests.ConnectionError(f"GET failed for {url}")

    client = MangoClient("key", "salt", session=Session())

    result = DownloadService(client, DownloadHistory(tmp_path / "history.json")).download([call("safe-recording-id")], tmp_path / "audio")

    contents = log_file.read_text(encoding="utf-8")
    assert result.errors == 1
    assert secret not in contents
    assert "Failed to download recording safe-recording-id" in contents
    assert "Recording download failed" in contents
