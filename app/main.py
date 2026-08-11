"""MANGO Downloader process entry point."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app import __version__
from app.core.logging_setup import configure_logging
from app.core.paths import AppPaths
from app.core.settings import SettingsStore
from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MANGO Downloader")
    try:
        paths = AppPaths.discover()
        created = paths.ensure_directories()
        logger = configure_logging(paths.log_file)
    except Exception as error:
        QMessageBox.critical(
            None,
            "MANGO Downloader",
            "Не удалось подготовить рабочую папку приложения.\n\n"
            "Переместите распакованную папку в Рабочий стол, Документы или Загрузки "
            "и повторите запуск. Права администратора не нужны.\n\n"
            f"Ошибка: {error}",
        )
        return 1

    def handle_exception(exc_type, exc_value, traceback) -> None:  # type: ignore[no-untyped-def]
        logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, traceback))
        QMessageBox.critical(
            None,
            "MANGO Downloader",
            f"Не удалось запустить приложение.\n\nПодробная информация записана в:\n{paths.log_file}",
        )

    sys.excepthook = handle_exception
    logger.info("Starting MANGO Downloader version %s", __version__)
    logger.info("Application root: %s", paths.root)
    for directory in created:
        logger.info("Created working directory: %s", directory)

    try:
        settings = SettingsStore(paths.settings_file, logger)
        settings.load()
        window = MainWindow(paths, settings)
        window.show()
        return app.exec()
    except Exception:
        logger.exception("Critical startup error")
        QMessageBox.critical(
            None,
            "MANGO Downloader",
            f"Не удалось запустить приложение.\n\nПодробная информация записана в:\n{paths.log_file}",
        )
        return 1
    finally:
        logger.info("MANGO Downloader stopped")


if __name__ == "__main__":
    raise SystemExit(main())
