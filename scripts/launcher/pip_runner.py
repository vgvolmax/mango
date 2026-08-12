"""Run the privately installed pip without relying on embedded-Python paths."""

from __future__ import annotations

import runpy
import sys


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: pip_runner.py <pip-dir> [pip arguments ...]")
    pip_dir, *pip_arguments = sys.argv[1:]
    sys.path.insert(0, pip_dir)
    sys.argv = ["pip", *pip_arguments]
    runpy.run_module("pip", run_name="__main__")


if __name__ == "__main__":
    main()

