import logging
from pathlib import Path

from app.core.logging_setup import configure_logging


def test_logging_creates_utf8_log_file(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "app.log"
    logger = configure_logging(log_file)
    logger.info("Запуск приложения")
    for handler in logger.handlers:
        handler.flush()

    assert log_file.is_file()
    assert "Запуск приложения" in log_file.read_text(encoding="utf-8")
    logger.handlers.clear()
