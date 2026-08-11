from datetime import datetime, timezone

from app.mango.models import CallDirection, CallRecord
from app.services.downloads import DownloadHistory, DownloadService, safe_filename


class Response:
    headers = {"Content-Type": "audio/mpeg"}
    def iter_content(self, _): return [b"mp3"]


class Client:
    def __init__(self): self.urls = 0
    def request_recording_url(self, _): self.urls += 1; return f"temporary-{self.urls}"
    def get_audio(self, url):
        if url == "temporary-1": raise RuntimeError("expired")
        return Response()


def call():
    return CallRecord("e", CallDirection.INCOMING, datetime(2026, 8, 11, tzinfo=timezone.utc), "7999", None, ("Иванов / Отдел",), 1, 1, ("r",))


def test_download_retries_with_fresh_url_then_skips_history(tmp_path):
    client = Client(); history = DownloadHistory(tmp_path / "history.json"); service = DownloadService(client, history)
    result = service.download([call()], tmp_path / "audio")
    assert result.downloaded == 1 and client.urls == 2
    assert not list(tmp_path.rglob("*.part"))
    assert service.download([call()], tmp_path / "audio").skipped == 1


def test_deleted_history_file_is_downloaded_again(tmp_path):
    service = DownloadService(Client(), DownloadHistory(tmp_path / "history.json"))
    service.download([call()], tmp_path / "audio")
    next((tmp_path / "audio").glob("*.mp3")).unlink()
    assert service.download([call()], tmp_path / "audio").downloaded == 1


def test_windows_safe_filename():
    value = safe_filename('<>:"/\\|?* Петров: тест? Иванов / Отдел ' + "я" * 300)
    assert not any(char in value for char in '<>:"/\\|?*')
    assert len(value) <= 180 and "Петров" in value
