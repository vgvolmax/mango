import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
START = (ROOT / "Start.bat").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "scripts/launcher/bootstrap.ps1").read_text(encoding="utf-8")


def test_batch_is_thin_root_relative_entry_point():
    lowered = START.lower()
    assert 'cd /d "%~dp0"' in lowered
    assert "powershell.exe" in lowered
    assert "%~dp0scripts\\launcher\\bootstrap.ps1" in lowered
    assert "%*" in START
    assert "python.exe" not in lowered and "pythonw.exe" not in lowered
    assert "if not defined ci pause" in lowered


def test_launcher_has_no_elevation_or_machine_modification():
    production = (START + "\n" + BOOTSTRAP).lower()
    forbidden = (
        "verb runas", 'shellexecute "runas"', "requireadministrator",
        "highestavailable", "schtasks", "sc.exe", "hklm", "setx",
    )
    assert all(term not in production for term in forbidden)
    assert not re.search(r"\brunas\b", production)


def test_bootstrap_uses_local_atomic_runtime_and_os_lock():
    assert 'Join-Path $Root "runtime"' in BOOTSTRAP
    assert "runtime.new-$unique" in BOOTSTRAP
    assert "runtime.old-$unique" in BOOTSTRAP
    assert "[IO.File]::Open" in BOOTSTRAP
    assert "'None'" in BOOTSTRAP
    assert "Invoke-WebRequest" in BOOTSTRAP
    assert "Test-Runtime" in BOOTSTRAP


def test_bootstrap_never_reads_credentials():
    lowered = BOOTSTRAP.lower()
    for secret in ("api_key", "api salt", "credentials.dat", "recording_url"):
        assert secret not in lowered


def test_manifest_is_exact_and_pinned():
    manifest = json.loads((ROOT / "scripts/launcher/runtime-manifest.json").read_text())
    assert set(manifest) == {"schema_version", "python", "pip"}
    assert manifest["schema_version"] == 1
    assert manifest["python"]["version"] == "3.12.8"
    for artifact in (manifest["python"], manifest["pip"]):
        assert set(artifact) == {"version", "url", "sha256"}
        assert artifact["url"].startswith("https://")
        assert re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])
        assert "latest" not in artifact["url"]


def test_dependency_lock_is_complete_and_exact():
    lock = (ROOT / "requirements/runtime-win-x64.lock.txt").read_text()
    expected = {"PySide6", "PySide6_Addons", "PySide6_Essentials", "shiboken6",
                "requests", "certifi", "charset-normalizer", "idna", "urllib3"}
    found = {line.split("==", 1)[0] for line in lock.splitlines() if line and not line.startswith("#")}
    assert found == expected
    assert all("==" in line for line in lock.splitlines() if line and not line.startswith("#"))


def test_runtime_receipt_guards_every_reuse_input():
    for field in ("python_version", "python_archive_sha256", "requirements_sha256",
                  "launcher_contract_version"):
        assert field in BOOTSTRAP
    for imported in ("app.main", "PySide6", "requests"):
        assert imported in BOOTSTRAP


def test_smoke_uses_prepared_runtime_and_constructs_window():
    assert "if ($Smoke)" in BOOTSTRAP
    assert 'Join-Path $Runtime "python.exe"' in BOOTSTRAP
    assert 'QT_QPA_PLATFORM = "offscreen"' in BOOTSTRAP
    assert "QApplication" in BOOTSTRAP and "MainWindow" in BOOTSTRAP
