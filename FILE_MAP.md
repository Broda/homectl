# File Map

This document is a quick orientation guide to the repository. It is intentionally short and should stay current as the project structure evolves.

## Top-Level Docs

- [`README.md`](README.md)
  Public project overview, install instructions, command overview, and wiki links.
- [`ROADMAP.md`](ROADMAP.md)
  Milestone-based planning document for upcoming work.
- [`ARCHITECTURE.md`](ARCHITECTURE.md)
  Current module boundaries, ownership notes, and public-contract guidance.
- [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md)
  Product scope, assumptions, and standard local verification commands.
- [`RELEASING.md`](RELEASING.md)
  Tagged release process, artifact flow, and publishing notes.
- [`CHANGELOG.md`](CHANGELOG.md)
  Human-facing release summary and notable project changes.
- [`FILE_MAP.md`](FILE_MAP.md)
  This file. Repository structure and ownership notes.

## Python Package

- [`homesrvctl/main.py`](homesrvctl/main.py)
  Typer CLI entrypoint that wires command groups together.
- [`homesrvctl/__init__.py`](homesrvctl/__init__.py)
  Package version and package marker.
- [`homesrvctl/models.py`](homesrvctl/models.py)
  Core dataclasses for config and stack-local settings.
- [`homesrvctl/config.py`](homesrvctl/config.py)
  Config loading, default paths, and stack-local config helpers.
- [`homesrvctl/utils.py`](homesrvctl/utils.py)
  Shared filesystem and rendering helpers.
- [`homesrvctl/templates.py`](homesrvctl/templates.py)
  Template rendering utilities.
- [`homesrvctl/shell.py`](homesrvctl/shell.py)
  Shared subprocess execution helpers.
- [`homesrvctl/tui`](homesrvctl/tui)
  Terminal UI implementation. This is the home for the current Textual app, the retained transitional curses renderer, and the JSON-backed data/action loading used by the TUI.
- [`homesrvctl/tui/app.py`](homesrvctl/tui/app.py)
  The current Textual app entrypoint for `homesrvctl tui`.
- [`homesrvctl/tui/dashboard.py`](homesrvctl/tui/dashboard.py)
  Older curses dashboard renderer that remains in the repo during the Textual migration.
- [`homesrvctl/tui/data.py`](homesrvctl/tui/data.py)
  JSON-backed data loading, action dispatch, and detail rendering helpers for the Textual TUI.
- [`homesrvctl/tui/prompts.py`](homesrvctl/tui/prompts.py)
  Small Textual prompt screens used by guided TUI flows such as template selection for scaffolding.

## Cloudflare And Cloudflared Helpers

- [`homesrvctl/cloudflare.py`](homesrvctl/cloudflare.py)
  Cloudflare DNS API integration and tunnel-target-related helpers.
- [`homesrvctl/cloudflared.py`](homesrvctl/cloudflared.py)
  `cloudflared` ingress config parsing, reconciliation, and validation helpers.
- [`homesrvctl/cloudflared_service.py`](homesrvctl/cloudflared_service.py)
  Runtime detection and restart/log command selection for `cloudflared`.

## CLI Commands

- [`homesrvctl/commands/config_cmd.py`](homesrvctl/commands/config_cmd.py)
  `config init` and related config-surface commands.
- [`homesrvctl/commands/site_cmd.py`](homesrvctl/commands/site_cmd.py)
  `site init` scaffold generation.
- [`homesrvctl/commands/app_cmd.py`](homesrvctl/commands/app_cmd.py)
  `app init` scaffold generation for app templates.
- [`homesrvctl/commands/deploy_cmd.py`](homesrvctl/commands/deploy_cmd.py)
  Stack lifecycle commands such as `up`, `down`, `restart`, `list`, and `doctor`.
- [`homesrvctl/commands/domain_cmd.py`](homesrvctl/commands/domain_cmd.py)
  Domain lifecycle commands such as `add`, `status`, `repair`, and `remove`.
- [`homesrvctl/commands/cloudflared_cmd.py`](homesrvctl/commands/cloudflared_cmd.py)
  `cloudflared` runtime and config-oriented commands.
- [`homesrvctl/commands/validate_cmd.py`](homesrvctl/commands/validate_cmd.py)
  Global validation and doctor/reporting helpers.
- [`homesrvctl/commands/tui_cmd.py`](homesrvctl/commands/tui_cmd.py)
  Thin CLI wrapper for launching the terminal UI.

## Templates

- [`homesrvctl/templates/app/placeholder`](homesrvctl/templates/app/placeholder)
  Minimal placeholder app scaffold.
- [`homesrvctl/templates/app/node`](homesrvctl/templates/app/node)
  Node app scaffold.
- [`homesrvctl/templates/app/python`](homesrvctl/templates/app/python)
  Python app scaffold.
- [`homesrvctl/templates/app/static`](homesrvctl/templates/app/static)
  Static nginx-backed app scaffold.
- [`homesrvctl/templates/app/static-api`](homesrvctl/templates/app/static-api)
  Static site plus small Python API scaffold.
- [`homesrvctl/templates/app/jekyll`](homesrvctl/templates/app/jekyll)
  Jekyll build-and-serve app scaffold.
- [`homesrvctl/templates/site`](homesrvctl/templates/site)
  Static site scaffold assets.

## CI And Release Automation

- [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
  Main CI workflow.
- [`.github/workflows/python-checks.yml`](.github/workflows/python-checks.yml)
  Reusable Python verification workflow used by CI and release automation.
- [`.github/workflows/release.yml`](.github/workflows/release.yml)
  Tagged release workflow for TestPyPI, PyPI, and GitHub Releases.

## Tests

- [`tests`](tests)
  Regression coverage for config, CLI behavior, JSON output, and release-adjacent behavior.

## Maintenance Notes

- Prefer updating this file when a new top-level doc is added.
- Prefer updating this file when a new command module or template family is added.
- Keep entries descriptive, but short enough to scan quickly.
