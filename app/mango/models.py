"""Normalized call domain model."""

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class CallDirection(IntEnum):
    INCOMING = 1
    OUTGOING = 2
    INTERNAL = 3

    @property
    def label(self) -> str:
        return {1: "Входящий", 2: "Исходящий", 3: "Внутренний"}[self.value]


@dataclass(frozen=True)
class CallRecord:
    entry_id: str
    direction: CallDirection
    started_at: datetime | None
    caller_number: str | None
    called_number: str | None
    employee_names: tuple[str, ...]
    duration_seconds: int
    talk_duration_seconds: int
    recording_ids: tuple[str, ...]

    @property
    def external_number(self) -> str:
        if self.direction == CallDirection.INCOMING:
            return self.caller_number or ""
        if self.direction == CallDirection.OUTGOING:
            return self.called_number or ""
        return f"{self.caller_number or ''} → {self.called_number or ''}".strip()
