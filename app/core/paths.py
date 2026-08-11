"""Centralized paths for source and portable executions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @classmethod
    def discover(cls) -> "AppPaths":
        override = os.environ.get("MANGO_APP_ROOT")
        root = Path(override) if override else Path(__file__).resolve().parents[2]
        return cls(root.resolve())

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def downloads_dir(self) -> Path:
        return self.root / "downloads"

    @property
    def credentials_file(self) -> Path:
        return self.data_dir / "credentials.dat"

    @property
    def download_history_file(self) -> Path:
        return self.data_dir / "download_history.json"

    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def log_file(self) -> Path:
        return self.logs_dir / "app.log"

    def ensure_directories(self) -> tuple[Path, ...]:
        created: list[Path] = []
        for directory in (self.data_dir, self.logs_dir, self.downloads_dir):
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                created.append(directory)
        return tuple(created)
