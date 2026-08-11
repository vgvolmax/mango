from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]


def test_start_bat_delegates_only_to_bootstrap():
    text = (ROOT / "Start.bat").read_text(encoding="utf-8").lower()

    for token in (
        "%~dp0",
        "chcp 65001",
        "pythonutf8",
        "pythonioencoding",
        "bootstrap.ps1",
        "%*",
    ):
        assert token in text

    assert "runtime\\pythonw.exe" not in text


def test_python_manifest_matches_auto_offer_reference():
    manifest = json.loads(
        (ROOT / "scripts/launcher/runtime-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["python"] == {
        "version": "3.13.7",
        "url": (
            "https://www.python.org/ftp/python/3.13.7/"
            "python-3.13.7-embed-amd64.zip"
        ),
        "sha256": (
            "f6cca216a359be84797cabb54149ce5e"
            "062afb16cc7567eb7fc51cacb2d86b65"
        ),
        "executable": "python.exe",
    }


def test_bootstrap_forbids_unsafe_or_competing_installers():
    paths = [
        ROOT / "Start.bat",
        ROOT / "scripts/launcher/bootstrap.ps1",
        ROOT / "scripts/launcher/runtime-manifest.json",
    ]
    text = "\n".join(p.read_text(encoding="utf-8") for p in paths).lower()

    for forbidden in (
        "pip.pyz",
        "get-pip.py",
        "ensurepip",
        "bootstrap.pypa.io",
        "invoke-webrequest",
        "get-filehash",
    ):
        assert forbidden not in text


def test_bootstrap_uses_auto_offer_security_primitives():
    text = (ROOT / "scripts/launcher/bootstrap.ps1").read_text(
        encoding="utf-8"
    ).lower()

    required = (
        "system.net.http",
        "allowautoredirect",
        "responseheadersread",
        ".lock(0,1)",
        "sha256]::create",
        "computehash",
        "python.new-",
        "install-receipt.json",
        "zipfile",
    )

    for token in required:
        assert token in text

    assert "get-filehash" not in text
    assert "invoke-webrequest" not in text


def test_bootstrap_downloader_matches_auto_offer_timeouts_and_async_read():
    text = (ROOT / "scripts/launcher/bootstrap.ps1").read_text(encoding="utf-8")

    assert "$client.Timeout = [TimeSpan]::FromSeconds(60)" in text
    assert "$cancellation.CancelAfter([TimeSpan]::FromMinutes(5))" in text
    assert "$input.ReadAsync(" in text
    assert "$cancellation.Token" in text
    assert "New-Object byte[] (256 * 1024)" in text
    assert "[Net.Http.HttpCompletionOption]::ResponseHeadersRead" in text
    assert "$response.Content.Headers.ContentLength" in text
    assert "$input.Read($buffer" not in text


def test_handoff_holds_lock_and_runtime_smoke_bypasses_launcher():
    text = (ROOT / "scripts/launcher/bootstrap.ps1").read_text(encoding="utf-8")
    runtime_branch = text.split("if ($RuntimeSmoke)", 1)[1].split("else", 1)[0]
    assert "launcher.py" not in runtime_branch
    assert "$env:MANGO_BOOTSTRAP_LOCK_HELD = '1'" in text
    assert "Remove-Item Env:MANGO_BOOTSTRAP_LOCK_HELD" in text
    assert text.index("Remove-Item Env:MANGO_BOOTSTRAP_LOCK_HELD") < text.index("$Lock.Unlock(0,1)")
