from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_portable_distribution_is_removed():
    assert not (ROOT / "Build-Portable.bat").exists()
    assert not (ROOT / "scripts" / "build_portable.ps1").exists()


def test_launcher_contract_declares_single_runtime_model():
    text = (ROOT / "docs" / "launcher-contract.md").read_text(encoding="utf-8").lower()

    assert ".runtime/" in text
    assert "auto_offer" in text
    assert "build-portable.bat" in text
    assert "must not be reintroduced" in text
