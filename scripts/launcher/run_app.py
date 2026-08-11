"""Expose portable application dependencies only to the application process."""

from __future__ import annotations

from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[2]
SITE_PACKAGES = ROOT / ".runtime" / "site-packages"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SITE_PACKAGES))


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "start"
    module = "app.smoke" if mode == "--smoke" else "app.main"
    runpy.run_module(module, run_name="__main__")


if __name__ == "__main__":
    main()

