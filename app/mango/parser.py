"""Tolerant conversion of statistics JSON into domain records."""

from datetime import datetime, timezone
from typing import Any, Iterable

from .models import CallDirection, CallRecord


def _walk_calls(calls: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for call in calls:
        yield call
        members = call.get("members")
        if isinstance(members, list):
            yield from _walk_calls(x for x in members if isinstance(x, dict))


def _timestamp(value: Any) -> datetime | None:
    try:
        number = float(value)
        if number > 10_000_000_000:  # API installations may return milliseconds.
            number /= 1000
        return datetime.fromtimestamp(number, timezone.utc).astimezone()
    except (TypeError, ValueError, OSError):
        return None


def parse_calls(payload: dict[str, Any]) -> list[CallRecord]:
    data = payload.get("data", payload)
    entries = data.get("list", []) if isinstance(data, dict) else []
    result: list[CallRecord] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        raw_direction = entry.get("context_type", 3)
        try:
            direction = CallDirection(int(raw_direction))
        except (TypeError, ValueError):
            direction = CallDirection.INTERNAL
        calls = list(_walk_calls(entry.get("context_calls", []) or []))
        recordings: list[str] = []
        names: list[str] = []
        for call in calls:
            raw_ids = call.get("recording_id", []) or []
            if not isinstance(raw_ids, list):
                raw_ids = [raw_ids]
            for recording_id in raw_ids:
                value = str(recording_id).strip()
                if value and value not in recordings:
                    recordings.append(value)
            if call.get("call_type") == "user":
                info = call.get("call_abonent_info")
                if isinstance(info, dict):
                    name = str(info.get("name") or info.get("fio") or "").strip()
                else:
                    name = str(info or "").strip()
                if name and name not in names:
                    names.append(name)
        result.append(CallRecord(
            entry_id=str(entry.get("entry_id", "")), direction=direction,
            started_at=_timestamp(entry.get("context_start_time")),
            caller_number=entry.get("caller_number"), called_number=entry.get("called_number"),
            employee_names=tuple(names), duration_seconds=int(entry.get("duration") or 0),
            talk_duration_seconds=int(entry.get("talk_duration") or 0),
            recording_ids=tuple(recordings),
        ))
    return result
