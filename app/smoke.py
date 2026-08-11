"""Offscreen construction smoke test for the packaged application."""

from __future__ import annotations

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.paths import AppPaths  # noqa: E402
from app.core.settings import SettingsStore  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    application = QApplication([])
    paths = AppPaths.discover()
    paths.ensure_directories()
    settings = SettingsStore(paths.settings_file)
    window = MainWindow(paths, settings)
    window.close()
    application.processEvents()
    print("MainWindow constructed offscreen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
