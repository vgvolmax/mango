from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_build_is_noninteractive():
    launcher = (ROOT / "Build-Portable.bat").read_text(encoding="utf-8")

    assert "-NoProfile -NonInteractive -ExecutionPolicy Bypass" in launcher
    assert launcher.count("%~dp0") >= 2


def test_build_python_installs_only_runtime_requirements_into_site_packages():
    script = (ROOT / "scripts" / "build_portable.ps1").read_text(encoding="utf-8")

    assert "get-pip.py" not in script
    assert "bootstrap.pypa.io" not in script
    assert "& $BuildPython -m pip install" in script
    assert "--target $SitePackages" in script
    assert 'requirements\\runtime-win-x64.lock.txt' in script
    assert "--only-binary=:all:" in script
    assert "--no-cache-dir" in script
    assert '"Lib\\site-packages"' in script
    assert "requirements\\dev.txt" not in script


def test_embedded_python_download_is_checked_before_expansion():
    script = (ROOT / "scripts" / "build_portable.ps1").read_text(encoding="utf-8")

    assert script.count("Invoke-WebRequest -UseBasicParsing") == 1
    assert "(Get-Item $PythonZip).Length -eq 0" in script
