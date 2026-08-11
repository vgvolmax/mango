from pathlib import Path

from app.core.paths import AppPaths


def test_paths_are_derived_from_root_and_directories_are_created(tmp_path: Path) -> None:
    root = tmp_path / "Тест Mango Downloader"
    paths = AppPaths(root)

    assert paths.data_dir == root / "data"
    assert paths.logs_dir == root / "logs"
    assert paths.settings_file == root / "data" / "settings.json"
    assert paths.downloads_dir == root / "downloads"
    assert paths.credentials_file == root / "data" / "credentials.dat"
    assert paths.download_history_file == root / "data" / "download_history.json"
    assert paths.ensure_directories() == (root / "data", root / "logs", root / "downloads")
    assert paths.data_dir.is_dir()
    assert paths.logs_dir.is_dir()


def test_discovery_does_not_depend_on_working_directory(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "portable folder"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("MANGO_APP_ROOT", str(root))
    monkeypatch.chdir(elsewhere)
    assert AppPaths.discover().root == root.resolve()
