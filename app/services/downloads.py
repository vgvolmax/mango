"""Safe recording downloads and minimal durable history."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from app.mango.models import CallRecord

INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(value: str, max_length: int = 180) -> str:
    clean = INVALID.sub("_", value).strip().rstrip(". ")
    return (clean[:max_length].rstrip(". ") or "recording")


def format_duration(seconds: int) -> str:
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


class DownloadHistory:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, value: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)


@dataclass
class DownloadSummary:
    downloaded: int = 0
    skipped: int = 0
    errors: int = 0


class DownloadService:
    def __init__(self, client, history: DownloadHistory, retries: int = 2) -> None:
        self.client, self.history, self.retries = client, history, retries
        self.logger = logging.getLogger(__name__)

    def download(self, calls: Iterable[CallRecord], directory: Path, progress: Callable[[int, int], None] | None = None) -> DownloadSummary:
        directory.mkdir(parents=True, exist_ok=True)
        jobs = [(call, rid, index) for call in calls for index, rid in enumerate(call.recording_ids, 1)]
        history, summary = self.history.load(), DownloadSummary()
        for done, (call, recording_id, index) in enumerate(jobs, 1):
            existing = history.get(recording_id, {}).get("path")
            if existing and Path(existing).is_file():
                summary.skipped += 1
            else:
                try:
                    path = self._download_one(call, recording_id, index, directory)
                    history[recording_id] = {"recording_id": recording_id, "downloaded_at": datetime.now(timezone.utc).isoformat(), "path": str(path)}
                    self.history.save(history)
                    summary.downloaded += 1
                except Exception:
                    self.logger.exception("Failed to download recording %s", recording_id)
                    summary.errors += 1
            if progress:
                progress(done, len(jobs))
        return summary

    def _download_one(self, call: CallRecord, recording_id: str, index: int, directory: Path) -> Path:
        started = call.started_at or datetime.now().astimezone()
        employee = "_".join(call.employee_names) or "Без_сотрудника"
        stem = safe_filename(f"{started:%Y-%m-%d_%H-%M-%S}_{call.direction.label}_{employee}_{call.external_number}_{index:02d}")
        target = directory / f"{stem}.mp3"
        suffix = 2
        while target.exists():
            target = directory / f"{stem}_{suffix}.mp3"; suffix += 1
        part = target.with_suffix(".mp3.part")
        try:
            for attempt in range(self.retries):
                try:
                    response = self.client.get_audio(self.client.request_recording_url(recording_id))
                    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                    if content_type and content_type not in {"audio/mp3", "audio/mpeg", "application/octet-stream"}:
                        raise ValueError("Unexpected recording content type")
                    wrote = 0
                    with part.open("wb") as stream:
                        for chunk in response.iter_content(64 * 1024):
                            if chunk: stream.write(chunk); wrote += len(chunk)
                    if not wrote: raise ValueError("Empty recording")
                    os.replace(part, target)
                    self.logger.info("Downloaded recording file %s", target.name)
                    return target
                except Exception:
                    part.unlink(missing_ok=True)
                    if attempt + 1 >= self.retries: raise
            raise RuntimeError("unreachable")
        finally:
            part.unlink(missing_ok=True)
