"""Secure, dependency-free downloader for portable launcher artifacts."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

CHUNK_SIZE = 256 * 1024
MAX_REDIRECTS = 10
RETRIES = 3
TIMEOUT = 60


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_url(url: str, allowed_hosts: set[str]) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Download URL must use HTTPS: {url}")
    if not parsed.hostname or parsed.hostname.casefold() not in allowed_hosts:
        raise ValueError(f"Download host is not allowed: {parsed.hostname}")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str]) -> None:
        self.allowed_hosts = allowed_hosts
        self.redirects = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        self.redirects += 1
        if self.redirects > MAX_REDIRECTS:
            raise urllib.error.HTTPError(newurl, code, "Too many redirects", headers, fp)
        absolute = urllib.parse.urljoin(req.full_url, newurl)
        _validate_url(absolute, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, absolute)


def _download_once(url: str, part: Path, allowed_hosts: set[str]) -> None:
    _validate_url(url, allowed_hosts)
    opener = urllib.request.build_opener(
        _SafeRedirectHandler(allowed_hosts),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    with opener.open(url, timeout=TIMEOUT) as response:
        _validate_url(response.geturl(), allowed_hosts)
        length = response.headers.get("Content-Length")
        expected = int(length) if length is not None else None
        received = 0
        with part.open("wb") as output:
            while chunk := response.read(CHUNK_SIZE):
                output.write(chunk)
                received += len(chunk)
        if expected is not None and received != expected:
            raise OSError(f"Incomplete download: received {received} of {expected} bytes")


def ensure_download(url: str, destination: Path, expected_sha256: str, hosts: list[str]) -> None:
    """Reuse a verified artifact, or securely download and atomically publish it."""
    expected_sha256 = expected_sha256.casefold()
    allowed_hosts = {host.casefold() for host in hosts}
    if destination.is_file() and sha256(destination) == expected_sha256:
        return
    destination.unlink(missing_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    for attempt in range(RETRIES):
        part.unlink(missing_ok=True)
        try:
            _download_once(url, part, allowed_hosts)
            if sha256(part) != expected_sha256:
                raise ValueError("Downloaded artifact SHA-256 does not match the manifest")
            os.replace(part, destination)
            return
        except (urllib.error.URLError, TimeoutError, OSError):
            part.unlink(missing_ok=True)
            if attempt + 1 == RETRIES:
                raise
            time.sleep(2)
        except Exception:
            part.unlink(missing_ok=True)
            raise

