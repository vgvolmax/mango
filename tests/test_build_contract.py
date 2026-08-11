from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_build_is_noninteractive_and_uses_basic_parsing():
    launcher = (ROOT / "Build-Portable.bat").read_text(encoding="utf-8")
    script = (ROOT / "scripts" / "build_portable.ps1").read_text(encoding="utf-8")

    assert "-NoProfile -NonInteractive -ExecutionPolicy Bypass" in launcher
    assert launcher.count("%~dp0") >= 2
    assert script.count("Invoke-WebRequest -UseBasicParsing") == 2
    assert script.count(".Length -eq 0") == 2
