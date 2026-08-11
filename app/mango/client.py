"""Centralized, timeout-bound MANGO HTTP client."""

import json
import logging
from contextlib import contextmanager
from typing import Any

import requests

from .auth import make_signature
from .errors import MangoApiError, MangoAuthenticationError, MangoNetworkError

MANGO_SUCCESS = 1000
FAILED_OPERATION_STATUSES = {"error", "cancel", "not-found"}


def _validate_api_result(value: dict[str, Any]) -> None:
    result = value.get("result")
    if isinstance(result, (int, float)) and not isinstance(result, bool):
        if result != MANGO_SUCCESS:
            raise MangoApiError(f"MANGO API returned result code {result}")

    status = str(value.get("status") or "").lower()
    if status in FAILED_OPERATION_STATUSES:
        raise MangoApiError(f"MANGO operation failed: {status}")


class MangoClient:
    BASE_URL = "https://app.mango-office.ru"

    def __init__(self, api_key: str, api_salt: str, *, session=None, timeout: float = 20) -> None:
        self.api_key, self._api_salt = api_key, api_salt
        self.session = session or requests.Session()
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)

    def _post_response(self, path: str, payload: dict[str, Any], **kwargs):
        json_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        form = {"vpbx_api_key": self.api_key, "sign": make_signature(self.api_key, json_text, self._api_salt), "json": json_text}
        self.logger.info("POST MANGO endpoint %s", path)
        try:
            response = self.session.post(self.BASE_URL + path, data=form, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise MangoNetworkError("MANGO network request failed") from exc
        if response.status_code in (401, 403):
            response.close()
            raise MangoAuthenticationError("MANGO rejected credentials")
        return response

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._post_response(path, payload)
        try:
            response.raise_for_status()
            value = response.json()
        except requests.RequestException as exc:
            raise MangoApiError(f"MANGO HTTP status {response.status_code}") from exc
        except (ValueError, TypeError) as exc:
            raise MangoApiError("MANGO returned malformed JSON") from exc
        if not isinstance(value, dict):
            raise MangoApiError("MANGO returned an unexpected response")
        _validate_api_result(value)
        return value

    def check_credentials(self) -> None:
        self.post("/vpbx/config/users/request", {})

    def request_statistics(self, payload: dict[str, Any]) -> str:
        value = self.post("/vpbx/stats/calls/request", payload)
        key = value.get("key")
        if not key:
            raise MangoApiError("MANGO did not return statistics key")
        return str(key)

    def statistics_result(self, key: str) -> dict[str, Any]:
        return self.post("/vpbx/stats/calls/result", {"key": key})

    @contextmanager
    def open_recording(self, recording_id: str):
        """Open a recording stream without exposing its temporary URL to callers."""
        redirect_response = self._post_response(
            "/vpbx/queries/recording/post",
            {"recording_id": recording_id, "action": "download"},
            allow_redirects=False,
        )
        try:
            if redirect_response.status_code != 302 or not redirect_response.headers.get("Location"):
                raise MangoApiError(f"MANGO recording response status {redirect_response.status_code}")
            temporary_url = redirect_response.headers["Location"]
        finally:
            redirect_response.close()

        response = None
        try:
            response = self.session.get(temporary_url, timeout=self.timeout, stream=True)
            response.raise_for_status()
            yield response
        except requests.RequestException:
            # Requests exceptions can embed the one-time URL in both their text and
            # traceback. Deliberately discard that exception chain at this boundary.
            raise MangoNetworkError("Recording download failed") from None
        finally:
            if response is not None:
                response.close()
