# MANGO Downloader project rules

## Product

This is a small Windows portable desktop application for downloading MANGO OFFICE call recordings.

## Architecture

Keep UI, application/domain logic, and infrastructure separate. Never put HTTP requests directly in GUI handlers.

## Portable and UX

The released application must not depend on system Python, `PATH`, installed `pip`, or manual user configuration. End users must not need a terminal, edit JSON, install dependencies, or see technical tracebacks.

## Engineering

- Apply YAGNI and keep modules small and focused.
- Do not introduce abstractions without an immediate use.
- Add tests for new business logic.
- Log errors, but never log secrets such as API keys or salts.

## Scope control

Do not implement functionality planned for a later PR unless it is explicitly requested.
