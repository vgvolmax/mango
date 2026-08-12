# MANGO Downloader Launcher Contract

## Canonical user flow

Download the repository folder
→ extract it completely
→ Start.bat
→ first-run local runtime preparation
→ application

## Runtime location

Only:

`.runtime/`

The legacy bundled `runtime/` distribution model is removed and must not be reintroduced.

## Reference implementation

Launcher architecture is based on:

`vgvolmax/auto_offer` main branch

Canonical flow:

Start.bat
→ scripts/launcher/bootstrap.ps1
→ .runtime/python
→ scripts/launcher/launcher.py
→ application

## Bootstrap rule

PR1 must port the working Auto Offer Python bootstrap mechanics with minimal changes.

The frozen PR1 layer owns Start.bat → bootstrap.ps1 → .runtime/python. Its
`--runtime-smoke` mode stops after validating Python.

Do not redesign:

- OS-backed lock
- HTTPS allowlist
- HttpClient downloader
- redirect handling
- retry
- SHA-256 implementation
- `.part` downloads
- ZIP-slip protection
- atomic Python publication
- install receipt
- offline reuse

Any deviation from Auto Offer must be explicitly justified in the PR description.

## Mango-specific layer

PowerShell owns portable Python only. After validating or repairing Python it
hands off under the same OS lock to the dependency-free `launcher.py`; it never
changes the published `.runtime/python` directory.

The Python launcher owns the verified pinned pip tool, the fully pinned
binary-only application dependency graph, and application launch. It installs
into staging directories, validates them, publishes them atomically, and records
their state. Dedicated stdlib runners add pip or application dependencies to the
child process `sys.path`; the embedded Python `_pth` file is never modified.
`--smoke` constructs and closes the GUI offscreen; normal launch spawns
`.runtime/python/pythonw.exe scripts/launcher/run_app.py start`.

## Forbidden competing architecture

Do not reintroduce:

- Build-Portable.bat
- scripts/build_portable.ps1
- dist/MangoDownloader-portable.zip as end-user distribution
- bundled `runtime/` as a canonical clean repository folder runtime
- system Python requirement
- admin/UAC requirement
