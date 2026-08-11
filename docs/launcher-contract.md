# MANGO Downloader Launcher Contract

## Canonical user flow

GitHub → Code → Download ZIP
→ extract completely
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

PR1 owns only Start.bat → bootstrap.ps1 → .runtime/python.

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

Mango-specific dependency installation and GUI launch belong to PR2, not PR1.

## Forbidden competing architecture

Do not reintroduce:

- Build-Portable.bat
- scripts/build_portable.ps1
- dist/MangoDownloader-portable.zip as end-user distribution
- bundled `runtime/` as canonical source-ZIP runtime
- system Python requirement
- admin/UAC requirement
