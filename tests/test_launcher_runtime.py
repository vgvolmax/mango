from pathlib import Path

import pytest

from scripts.launcher.launcher import parse_lock_file


VALID_HASH = "a" * 64


def test_lock_parser_normalizes_names_and_returns_pins_and_hashes(tmp_path: Path):
    lock = tmp_path / "runtime.lock"
    lock.write_text(
        f"PySide6==1.2.3 \\\n    --hash=sha256:{VALID_HASH} \\\n    --hash=sha256:{'b' * 64}\n"
        f"Requests==4.5.6 \\\n    --hash=sha256:{'c' * 64}\n",
        encoding="utf-8",
    )

    parsed = parse_lock_file(lock)
    assert parsed.pins == {"pyside6": "1.2.3", "requests": "4.5.6"}
    assert parsed.hashes == {
        "pyside6": (VALID_HASH, "b" * 64),
        "requests": ("c" * 64,),
    }


@pytest.mark.parametrize(
    "invalid",
    [
        "PySide6==1\n",
        f"PySide6==1 \\\n    --hash=md5:{VALID_HASH}\n",
        "PySide6==1 \\\n    --hash=sha256:123\n",
        f"PySide6==1 \\\n    --hash=sha256:{VALID_HASH}\n--index-url https://example.com\n",
        f"requests>=1 \\\n    --hash=sha256:{VALID_HASH}\n",
        f"package @ https://example.com/package.whl \\\n    --hash=sha256:{VALID_HASH}\n",
        f"PySide6==1 \\\n    --hash=sha256:{VALID_HASH}\npyside6==1 \\\n    --hash=sha256:{'b' * 64}\nrequests==1 \\\n    --hash=sha256:{'c' * 64}\n",
        f"PySide6==1 \\\n    --hash=sha256:{VALID_HASH} \\\n    --hash=sha256:{VALID_HASH}\nrequests==1 \\\n    --hash=sha256:{'c' * 64}\n",
    ],
)
def test_lock_parser_rejects_unsafe_unhashed_or_duplicate_requirements(tmp_path: Path, invalid: str):
    lock = tmp_path / "runtime.lock"
    lock.write_text(invalid, encoding="utf-8")

    with pytest.raises(ValueError):
        parse_lock_file(lock)


def test_lock_parser_requires_application_entry_packages(tmp_path: Path):
    lock = tmp_path / "runtime.lock"
    lock.write_text(
        f"requests==1 \\\n    --hash=sha256:{VALID_HASH}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="PySide6 and requests"):
        parse_lock_file(lock)
