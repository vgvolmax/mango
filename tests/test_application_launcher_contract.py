import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_pins_production_pip_wheel():
    manifest = json.loads((ROOT / "scripts/launcher/runtime-manifest.json").read_text())
    assert manifest["pip"] == {
        "version": "24.3.1",
        "url": "https://files.pythonhosted.org/packages/ef/7d/500c9ad20238fcfcb4cb9243eede163594d7020ce87bd9610c9e02771876/pip-24.3.1-py3-none-any.whl",
        "sha256": "3790624780082365f47549d032f3770eeb2b1e8bd1f7b2e02dace1afa361b4ed",
    }
    all_launcher_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "scripts/launcher").iterdir() if path.is_file()
    ).lower()
    assert "pip.pyz" not in all_launcher_text
    assert "get-pip.py" not in all_launcher_text


def test_runtime_lock_is_complete_and_exact():
    lines = [line for line in (ROOT / "requirements/runtime-win-x64.lock.txt").read_text().splitlines() if line]
    assert len(lines) == 9
    assert all(line.count("==") == 1 for line in lines)


def test_launcher_stages_validates_receipt_and_spawns_gui():
    text = (ROOT / "scripts/launcher/launcher.py").read_text(encoding="utf-8")
    for token in ("--only-binary=:all:", "site-packages.new-", "dependencies-receipt.json", "distributions(path=", "pythonw.exe", '"-m", "app.main"', "subprocess.Popen", "shell=False"):
        assert token in text
    assert "PYTHONPATH" not in text


def test_smoke_modes_keep_python_gate_separate():
    bootstrap = (ROOT / "scripts/launcher/bootstrap.ps1").read_text(encoding="utf-8")
    runtime_branch = bootstrap.split("if ($RuntimeSmoke)", 1)[1].split("else", 1)[0]
    assert "launcher.py" not in runtime_branch
    assert "Install-PipTool" not in runtime_branch
    assert "--smoke" in bootstrap and "launcher.py" in bootstrap
