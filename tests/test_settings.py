import json
import logging
from pathlib import Path

from app.core.settings import DEFAULT_SETTINGS, SettingsStore


def test_first_load_creates_default_settings(tmp_path: Path) -> None:
    path = tmp_path / "data" / "settings.json"
    result = SettingsStore(path).load()
    assert result == DEFAULT_SETTINGS
    assert json.loads(path.read_text(encoding="utf-8")) == DEFAULT_SETTINGS


def test_existing_settings_are_loaded(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"version": 1, "theme": "system"}', encoding="utf-8")
    assert SettingsStore(path).load() == {"version": 1, "theme": "system"}


def test_settings_save_replaces_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("old", encoding="utf-8")
    SettingsStore(path).save({"version": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1}
    assert not path.with_suffix(".json.tmp").exists()


def test_broken_settings_use_defaults_and_are_logged(tmp_path: Path, caplog) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{ broken json", encoding="utf-8")
    logger = logging.getLogger("settings-test")
    with caplog.at_level(logging.ERROR, logger="settings-test"):
        result = SettingsStore(path, logger).load()
    assert result == DEFAULT_SETTINGS
    assert "using defaults" in caplog.text
