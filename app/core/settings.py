"""Small, resilient JSON settings store."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS: dict[str, Any] = {"version": 1}


class SettingsStore:
    def __init__(self, path: Path, logger: logging.Logger | None = None) -> None:
        self.path = path
        self.logger = logger or logging.getLogger(__name__)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            defaults = DEFAULT_SETTINGS.copy()
            self.save(defaults)
            return defaults
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("settings root must be a JSON object")
            return value
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            self.logger.exception("Could not read settings; using defaults")
            return DEFAULT_SETTINGS.copy()

    def save(self, settings: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
