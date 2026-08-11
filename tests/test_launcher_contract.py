import importlib.util
import json
import re
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "launcher" / "launcher.py"


def launcher_module():
    spec = importlib.util.spec_from_file_location("mango_launcher", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_start_bat_uses_auto_offer_style_bootstrap():
    text = (ROOT / "Start.bat").read_text(encoding="utf-8").lower()
    for token in ("%~dp0", "chcp 65001", "pythonutf8", "pythonioencoding", "bootstrap.ps1", "%*"):
        assert token in text


def test_launcher_production_path_never_elevates_or_uses_system_python():
    files = [ROOT / "Start.bat", ROOT / "scripts" / "launcher" / "bootstrap.ps1", LAUNCHER]
    text = "\n".join(path.read_text(encoding="utf-8") for path in files).lower()
    forbidden = ("runas", "verb runas", "requireadministrator", "highestavailable", "hklm", "setx", "where python", "py.exe", "--user", "python -m pip")
    for token in forbidden:
        assert token not in text


def test_runtime_manifest_pins_verified_artifacts():
    manifest = json.loads((ROOT / "scripts" / "launcher" / "runtime-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["python"] == {
        "version": "3.13.7",
        "url": "https://www.python.org/ftp/python/3.13.7/python-3.13.7-embed-amd64.zip",
        "sha256": "f6cca216a359be84797cabb54149ce5e062afb16cc7567eb7fc51cacb2d86b65",
        "executable": "python.exe",
    }
    assert manifest["pip"]["version"] == "24.3.1"
    assert manifest["pip"]["url"] == "https://bootstrap.pypa.io/pip/zipapp/pip-24.3.1.pyz"
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["pip"]["sha256"])
    assert all(item["url"].startswith("https://") for item in (manifest["python"], manifest["pip"]))
    assert "latest" not in json.dumps(manifest).lower()


def test_windows_dependency_lock_is_complete_and_exact():
    lines = [line.strip() for line in (ROOT / "requirements" / "runtime-win-x64.lock.txt").read_text().splitlines() if line.strip() and not line.startswith("#")]
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+", line) for line in lines)
    names = {line.split("==", 1)[0].lower().replace("_", "-") for line in lines}
    assert names == {"pyside6", "pyside6-addons", "pyside6-essentials", "shiboken6", "requests", "certifi", "charset-normalizer", "idna", "urllib3"}


def test_ready_dependencies_skip_installer(tmp_path):
    module = launcher_module()
    install = Mock()
    assert module.ensure_dependencies(tmp_path, {"python": {"version": "3.13.7"}, "pip": {"version": "24.3.1"}}, validate=Mock(return_value=True), install=install) is False
    install.assert_not_called()
