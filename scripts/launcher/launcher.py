"""Dependency lifecycle and application launch for the embedded runtime."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

CONTRACT_VERSION = 1


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def expected_receipt(root: Path, manifest: dict) -> dict:
    return {
        "schema_version": 1,
        "python_version": manifest["python"]["version"],
        "pip_version": manifest["pip"]["version"],
        "requirements_sha256": file_sha256(root / "requirements" / "runtime-win-x64.lock.txt"),
        "launcher_contract_version": CONTRACT_VERSION,
    }


def dependencies_ready(root: Path, manifest: dict) -> bool:
    receipt_path = root / ".runtime" / "dependencies-receipt.json"
    site = root / ".runtime" / "site-packages"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    if receipt != expected_receipt(root, manifest) or not site.is_dir():
        return False
    check = subprocess.run(
        [str(root / ".runtime" / "python" / "python.exe"), "-c", "import PySide6, requests, app.main"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    return check.returncode == 0


def install_dependencies(root: Path, manifest: dict) -> None:
    runtime = root / ".runtime"
    staging = runtime / f"site-packages.new-{uuid.uuid4().hex}"
    active = runtime / "site-packages"
    old = runtime / "site-packages.old"
    staging.mkdir(parents=True)
    command = [
        str(runtime / "python" / "python.exe"),
        str(runtime / "downloads" / f"pip-{manifest['pip']['version']}.pyz"),
        "install", "--disable-pip-version-check", "--only-binary=:all:", "--no-cache-dir",
        "--target", str(staging), "-r", str(root / "requirements" / "runtime-win-x64.lock.txt"),
    ]
    try:
        result = subprocess.run(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        with (runtime / "logs" / "launcher.log").open("a", encoding="utf-8") as log:
            log.write(result.stdout)
        if result.returncode:
            raise RuntimeError(f"pip bootstrap exited with code {result.returncode}")
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((str(staging), str(root)))
        validation = subprocess.run(
            [command[0], "-c", "import PySide6, requests, app.main"], cwd=root, env=env, check=False
        )
        if validation.returncode:
            raise RuntimeError("installed dependencies failed import validation")
        if old.exists():
            shutil.rmtree(old)
        if active.exists():
            active.replace(old)
        try:
            staging.replace(active)
        except Exception:
            if old.exists() and not active.exists():
                old.replace(active)
            raise
        (runtime / "dependencies-receipt.json").write_text(
            json.dumps(expected_receipt(root, manifest), indent=2) + "\n", encoding="utf-8"
        )
        shutil.rmtree(old, ignore_errors=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def ensure_dependencies(root: Path, manifest: dict, *, validate=dependencies_ready, install=install_dependencies) -> bool:
    if validate(root, manifest):
        return False
    install(root, manifest)
    if not dependencies_ready(root, manifest):
        raise RuntimeError("dependency validation failed after installation")
    return True


def smoke(root: Path) -> int:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["MANGO_APP_ROOT"] = str(root)
    code = """from PySide6.QtWidgets import QApplication
from app.core.paths import AppPaths
from app.core.settings import SettingsStore
from app.ui.main_window import MainWindow
app=QApplication([]); paths=AppPaths.discover(); paths.ensure_directories(); window=MainWindow(paths, SettingsStore(paths.settings_file)); window.close(); app.processEvents()
"""
    return subprocess.run([str(root / ".runtime/python/python.exe"), "-c", code], cwd=root, env=env).returncode


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((Path(__file__).with_name("runtime-manifest.json")).read_text(encoding="utf-8"))
    print("[2/4] Компоненты приложения")
    changed = ensure_dependencies(root, manifest)
    print("[2/4] Компоненты приложения: " + ("подготовлены" if changed else "готовы"))
    print("[3/4] Проверка: OK")
    if "--smoke" in sys.argv[1:]:
        return smoke(root)
    print("[4/4] Запуск MANGO Downloader")
    env = os.environ.copy(); env["MANGO_APP_ROOT"] = str(root)
    return subprocess.Popen([str(root / ".runtime/python/pythonw.exe"), "-m", "app.main"], cwd=root, env=env).wait()


if __name__ == "__main__":
    raise SystemExit(main())
