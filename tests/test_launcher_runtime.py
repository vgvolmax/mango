from pathlib import Path

import pytest

from scripts.launcher.launcher import parse_lock_file


def test_lock_parser_normalizes_names_and_returns_all_exact_pins(tmp_path: Path):
    lock = tmp_path / "runtime.lock"
    lock.write_text(
        "PySide6==1.2.3\nRequests==4.5.6\ncharset_normalizer==7.8.9\n",
        encoding="utf-8",
    )

    assert parse_lock_file(lock) == {
        "pyside6": "1.2.3",
        "requests": "4.5.6",
        "charset-normalizer": "7.8.9",
    }


@pytest.mark.parametrize(
    "invalid",
    [
        "PySide6>=1\nrequests==1\n",
        "PySide6==1; python_version>'3'\nrequests==1\n",
        "PySide6 @ https://example.invalid/package.whl\nrequests==1\n",
        "-r other.txt\nPySide6==1\nrequests==1\n",
        "--index-url https://example.invalid\nPySide6==1\nrequests==1\n",
        "-e example\nPySide6==1\nrequests==1\n",
        "PySide6==1\npyside6==1\nrequests==1\n",
    ],
)
def test_lock_parser_rejects_non_exact_or_duplicate_requirements(tmp_path: Path, invalid: str):
    lock = tmp_path / "runtime.lock"
    lock.write_text(invalid, encoding="utf-8")

    with pytest.raises(ValueError):
        parse_lock_file(lock)


def test_lock_parser_requires_application_entry_packages(tmp_path: Path):
    lock = tmp_path / "runtime.lock"
    lock.write_text("requests==1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="PySide6 and requests"):
        parse_lock_file(lock)
