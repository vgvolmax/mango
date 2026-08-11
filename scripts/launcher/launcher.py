"""Prepare pinned application dependencies and start MANGO Downloader."""

from __future__ import annotations

import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

PYTHON_VERSION = "3.13.7"
PIP_VERSION = "24.3.1"
CONTRACT_VERSION = 2
EXPECTED_PACKAGES = {"pyside6": "6.8.1", "requests": "2.32.3"}

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime"
SITE_PACKAGES = RUNTIME / "site-packages"
REQUIREMENTS = ROOT / "requirements" / "runtime-win-x64.lock.txt"
RECEIPT = RUNTIME / "dependencies-receipt.json"
LOG_PATH = RUNTIME / "logs" / "launcher.log"


def configure_logger() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("mango.launcher")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=4, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s stage=%(stage)s %(message)s"))
    logger.handlers[:] = [handler]
    return logger


def requirements_sha256() -> str:
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def expected_receipt() -> dict[str, object]:
    return {
        "schema_version": 1,
        "python_version": PYTHON_VERSION,
        "pip_version": PIP_VERSION,
        "requirements_sha256": requirements_sha256(),
        "launcher_contract_version": CONTRACT_VERSION,
    }


def validation_code(directory: Path) -> str:
    # Remove the active dependency directory before adding the candidate. This makes
    # staging validation unable to succeed by accidentally importing an old install.
    return f"""
import sys
from importlib.metadata import distributions
active = {str(SITE_PACKAGES)!r}.casefold()
sys.path[:] = [p for p in sys.path if p.casefold() != active]
sys.path.insert(0, {str(ROOT)!r})
sys.path.insert(0, {str(directory)!r})
import PySide6
import requests
import app.main
versions = {{d.metadata['Name'].casefold(): d.version for d in distributions(path=[{str(directory)!r}])}}
assert versions.get('pyside6') == '6.8.1', versions
assert versions.get('requests') == '2.32.3', versions
"""


def validate(directory: Path) -> bool:
    if not directory.is_dir():
        return False
    result = subprocess.run(
        [sys.executable, "-c", validation_code(directory)],
        cwd=ROOT,
        shell=False,
        check=False,
    )
    return result.returncode == 0


def dependencies_ready() -> bool:
    try:
        if json.loads(RECEIPT.read_text(encoding="utf-8-sig")) != expected_receipt():
            return False
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return validate(SITE_PACKAGES)


def install_dependencies(logger: logging.Logger) -> None:
    staging = RUNTIME / f"site-packages.new-{os.getpid()}-{uuid.uuid4().hex}"
    old = RUNTIME / f"site-packages.old-{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        command = [
            sys.executable, "-m", "pip", "install",
            "--disable-pip-version-check", "--no-input", "--no-cache-dir",
            "--no-compile", "--only-binary=:all:", "--target", str(staging),
            "-r", str(REQUIREMENTS),
        ]
        logger.info("Installing pinned binary dependencies into staging", extra={"stage": "dependencies"})
        subprocess.run(command, cwd=ROOT, shell=False, check=True)
        if not validate(staging):
            raise RuntimeError("Staged dependencies failed import or version validation")

        shutil.rmtree(old, ignore_errors=True)
        had_active = SITE_PACKAGES.exists()
        if had_active:
            SITE_PACKAGES.replace(old)
        try:
            staging.replace(SITE_PACKAGES)
        except Exception:
            if had_active and not SITE_PACKAGES.exists():
                old.replace(SITE_PACKAGES)
            raise
        shutil.rmtree(old, ignore_errors=True)
        temporary = RECEIPT.with_suffix(".json.new")
        temporary.write_text(json.dumps(expected_receipt(), indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, RECEIPT)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def launch(mode: str, logger: logging.Logger) -> int:
    environment = os.environ.copy()
    environment.update(MANGO_APP_ROOT=str(ROOT), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    if mode == "--smoke":
        return subprocess.run(
            [sys.executable, "-m", "app.smoke"], cwd=ROOT, env=environment,
            shell=False, check=False,
        ).returncode
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen(
        [str(pythonw), "-m", "app.main"], cwd=ROOT, env=environment,
        shell=False,
    )
    logger.info("GUI process started", extra={"stage": "launch"})
    return 0


def main() -> int:
    logger = configure_logger()
    mode = sys.argv[1] if len(sys.argv) > 1 else "start"
    try:
        if not dependencies_ready():
            install_dependencies(logger)
        else:
            logger.info("Pinned dependencies are ready; installation skipped", extra={"stage": "dependencies"})
        return launch(mode, logger)
    except Exception:
        logger.exception("Launcher preparation failed", extra={"stage": "failure"})
        print(
            "MANGO Downloader could not start.\n"
            "Stage: portable dependency preparation.\n"
            "The prepared Python and verified downloads were preserved.\n"
            "The dependency step will be retried next time.\n"
            f"Details: {LOG_PATH}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
