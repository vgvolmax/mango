"""Prepare pinned pip and application dependencies, then start MANGO."""

from __future__ import annotations

import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from typing import NamedTuple

LAUNCHER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAUNCHER_DIR))
from portable_download import ensure_download

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime"
PIP_DIR = RUNTIME / "pip"
SITE_PACKAGES = RUNTIME / "site-packages"
MANIFEST_PATH = LAUNCHER_DIR / "runtime-manifest.json"
REQUIREMENTS = ROOT / "requirements" / "runtime-win-x64.lock.txt"
RECEIPT = RUNTIME / "dependencies-receipt.json"
LOG_PATH = RUNTIME / "logs" / "launcher.log"
PIP_RUNNER = Path(__file__).with_name("pip_runner.py")
RUN_APP = Path(__file__).with_name("run_app.py")
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)$")
HASH = re.compile(r"^--hash=sha256:([0-9a-f]{64})$")


class HashedLock(NamedTuple):
    pins: dict[str, str]
    hashes: dict[str, tuple[str, ...]]


def configure_logger() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("mango.launcher")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=4, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s stage=%(stage)s %(message)s"))
    logger.handlers[:] = [handler]
    return logger


def load_manifest() -> dict[str, object]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported runtime manifest schema")
    for key in ("launcher_version", "python", "pip", "download_hosts"):
        if not manifest.get(key):
            raise ValueError(f"Runtime manifest is missing {key}")
    pip = manifest["pip"]
    python = manifest["python"]
    if not isinstance(pip, dict) or not isinstance(python, dict):
        raise ValueError("Invalid runtime manifest sections")
    for section in (pip, python):
        if not section.get("version") or not section.get("sha256"):
            raise ValueError("Runtime manifest artifact is incomplete")
    if not pip.get("url") or not re.fullmatch(r"[0-9a-f]{64}", str(pip["sha256"])):
        raise ValueError("Invalid pip artifact manifest")
    return manifest


def parse_lock_file(path: Path = REQUIREMENTS) -> HashedLock:
    pins: dict[str, str] = {}
    hashes: dict[str, tuple[str, ...]] = {}
    physical_lines = path.read_text(encoding="utf-8-sig").splitlines()
    logical: list[tuple[int, list[str]]] = []
    parts: list[str] = []
    start = 0
    for number, raw in enumerate(physical_lines, 1):
        if not raw.strip():
            if parts:
                raise ValueError(f"Invalid requirement at line {start}: incomplete continuation")
            continue
        if not parts:
            start = number
        stripped = raw.strip()
        continued = stripped.endswith("\\")
        token = stripped[:-1].rstrip() if continued else stripped
        if not token:
            raise ValueError(f"Invalid requirement at line {number}")
        parts.append(token)
        if not continued:
            logical.append((start, parts))
            parts = []
    if parts:
        raise ValueError(f"Invalid requirement at line {start}: incomplete continuation")

    for number, tokens in logical:
        match = PIN.fullmatch(tokens[0])
        if not match:
            raise ValueError(f"Invalid requirement at line {number}: exact name==version pins only")
        name, version = match.groups()
        normalized = name.casefold().replace("_", "-").replace(".", "-")
        if normalized in pins:
            raise ValueError(f"Duplicate requirement at line {number}: {name}")
        requirement_hashes: list[str] = []
        for token in tokens[1:]:
            hash_match = HASH.fullmatch(token)
            if not hash_match:
                raise ValueError(f"Invalid requirement hash at line {number}")
            digest = hash_match.group(1)
            if digest in requirement_hashes:
                raise ValueError(f"Duplicate requirement hash at line {number}: {name}")
            requirement_hashes.append(digest)
        if not requirement_hashes:
            raise ValueError(f"Requirement at line {number} has no SHA256 hash: {name}")
        pins[normalized] = version
        hashes[normalized] = tuple(requirement_hashes)
    if not {"pyside6", "requests"}.issubset(pins):
        raise ValueError("Runtime lock must pin PySide6 and requests")
    return HashedLock(pins, hashes)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pip_receipt(manifest: dict[str, object]) -> dict[str, object]:
    pip = manifest["pip"]
    assert isinstance(pip, dict)
    return {"schema_version": 1, "version": pip["version"], "sha256": pip["sha256"]}


def dependency_receipt(manifest: dict[str, object]) -> dict[str, object]:
    python, pip = manifest["python"], manifest["pip"]
    assert isinstance(python, dict) and isinstance(pip, dict)
    return {
        "schema_version": 1,
        "launcher_version": manifest["launcher_version"],
        "python_version": python["version"],
        "pip_version": pip["version"],
        "pip_sha256": pip["sha256"],
        "requirements_sha256": _hash(REQUIREMENTS),
    }


def _receipt_matches(path: Path, expected: dict[str, object]) -> bool:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")) == expected
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False


def _write_receipt(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(path.name + f".new-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def validate_pip(directory: Path, manifest: dict[str, object]) -> bool:
    if not directory.is_dir() or not _receipt_matches(directory / "install-receipt.json", pip_receipt(manifest)):
        return False
    pip = manifest["pip"]
    assert isinstance(pip, dict)
    result = subprocess.run(
        [sys.executable, str(PIP_RUNNER), str(directory), "--version"],
        cwd=ROOT, shell=False, check=False, capture_output=True, text=True,
    )
    return result.returncode == 0 and str(pip["version"]) in result.stdout


def prepare_pip(manifest: dict[str, object], logger: logging.Logger) -> None:
    pip = manifest["pip"]
    assert isinstance(pip, dict)
    wheel = RUNTIME / "downloads" / f"pip-{pip['version']}-py3-none-any.whl"
    ensure_download(str(pip["url"]), wheel, str(pip["sha256"]), list(manifest["download_hosts"]))
    if validate_pip(PIP_DIR, manifest):
        logger.info("Pinned pip is ready; preparation skipped", extra={"stage": "pip"})
        return
    for stale in RUNTIME.glob("pip.new-*"):
        if stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)
    staging = RUNTIME / f"pip.new-{os.getpid()}-{uuid.uuid4().hex}"
    old = RUNTIME / f"pip.old-{os.getpid()}-{uuid.uuid4().hex}"
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(wheel) as archive:
            root = staging.resolve()
            for member in archive.infolist():
                if re.search(r"(^|/)[^/]+\.data/", member.filename):
                    raise ValueError("Pinned pip wheel unexpectedly contains a .data layout")
                target = (staging / member.filename).resolve()
                if target != root and root not in target.parents:
                    raise ValueError(f"Unsafe pip wheel entry: {member.filename}")
            archive.extractall(staging)
        _write_receipt(staging / "install-receipt.json", pip_receipt(manifest))
        if not validate_pip(staging, manifest):
            raise RuntimeError("Staged pip tool failed validation")
        _publish(staging, PIP_DIR, old)
        logger.info("Pinned pip was prepared", extra={"stage": "pip"})
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def validation_code(directory: Path, pins: dict[str, str]) -> str:
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
normalize = lambda name: name.casefold().replace('_', '-').replace('.', '-')
versions = {{normalize(d.metadata['Name']): d.version for d in distributions(path=[{str(directory)!r}])}}
assert versions == {pins!r}, (versions, {pins!r})
"""


def validate_dependencies(directory: Path, pins: dict[str, str]) -> bool:
    if not directory.is_dir():
        return False
    return subprocess.run(
        [sys.executable, "-c", validation_code(directory, pins)],
        cwd=ROOT, shell=False, check=False,
    ).returncode == 0


def _publish(staging: Path, active: Path, old: Path) -> None:
    shutil.rmtree(old, ignore_errors=True)
    had_active = active.exists()
    if had_active:
        active.replace(old)
    try:
        staging.replace(active)
    except Exception:
        if had_active and not active.exists():
            old.replace(active)
        raise
    shutil.rmtree(old, ignore_errors=True)


def prepare_dependencies(manifest: dict[str, object], pins: dict[str, str], logger: logging.Logger) -> None:
    expected = dependency_receipt(manifest)
    if _receipt_matches(RECEIPT, expected) and validate_dependencies(SITE_PACKAGES, pins):
        logger.info("Pinned dependencies are ready; installation skipped", extra={"stage": "dependencies"})
        return
    for stale in RUNTIME.glob("site-packages.new-*"):
        if stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)
    staging = RUNTIME / f"site-packages.new-{os.getpid()}-{uuid.uuid4().hex}"
    old = RUNTIME / f"site-packages.old-{os.getpid()}-{uuid.uuid4().hex}"
    staging.mkdir(parents=True)
    try:
        command = [
            sys.executable, str(PIP_RUNNER), str(PIP_DIR), "--isolated", "install",
            "--disable-pip-version-check", "--no-input", "--no-cache-dir",
            "--no-compile", "--require-hashes", "--no-deps",
            "--only-binary=:all:", "--target", str(staging),
            "-r", str(REQUIREMENTS),
        ]
        subprocess.run(command, cwd=ROOT, shell=False, check=True)
        if not validate_dependencies(staging, pins):
            raise RuntimeError("Staged dependencies failed validation")
        _publish(staging, SITE_PACKAGES, old)
        _write_receipt(RECEIPT, expected)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def launch(mode: str, logger: logging.Logger) -> int:
    environment = os.environ.copy()
    environment.update(MANGO_APP_ROOT=str(ROOT), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    if mode == "--smoke":
        return subprocess.run(
            [sys.executable, str(RUN_APP), "--smoke"], cwd=ROOT, env=environment,
            shell=False, check=False,
        ).returncode
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen(
        [str(pythonw), str(RUN_APP), "start"], cwd=ROOT, env=environment, shell=False,
    )
    logger.info("GUI process started", extra={"stage": "launch"})
    return 0


def main() -> int:
    logger = configure_logger()
    try:
        if os.environ.get("MANGO_BOOTSTRAP_LOCK_HELD") != "1":
            raise RuntimeError("launcher mutations must run under bootstrap lock")
        manifest = load_manifest()
        lock = parse_lock_file()
        prepare_pip(manifest, logger)
        prepare_dependencies(manifest, lock.pins, logger)
        mode = sys.argv[1] if len(sys.argv) > 1 else "start"
        return launch(mode, logger)
    except Exception:
        logger.exception("Launcher preparation failed", extra={"stage": "failure"})
        print(
            "MANGO Downloader could not start. See .runtime/logs/launcher.log; "
            "preparation will be retried next time.", file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
