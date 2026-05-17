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
- [`scripts/check_wiki_sync.sh`](scripts/check_wiki_sync.sh)
  Advisory check that reminds you to update the sibling GitHub wiki checkout when user-facing repo surfaces changed.

## Project Tooling

- [`pyproject.toml`](pyproject.toml)
  Python package metadata, dependencies, build backend, console script, and pytest defaults.
- [`uv.lock`](uv.lock)
  uv-managed dependency lockfile for local development, verification, CI, and builds.
- [`.python-version`](.python-version)
  Local uv/Python default version pin for development; CI still tests the supported Python matrix.

## Python Package

- [`homesrvctl/main.py`](homesrvctl/main.py)
  Typer CLI entrypoint that wires command groups together.
- [`homesrvctl/__init__.py`](homesrvctl/__init__.py)
  Package version and package marker.
- [`homesrvctl/models.py`](homesrvctl/models.py)
  Core dataclasses for config and stack-local settings.
- [`homesrvctl/config.py`](homesrvctl/config.py)
  Config loading, default paths, and stack-local config helpers.
- [`homesrvctl/ports.py`](homesrvctl/ports.py)
  Rendered-stack port inspection helpers used for port reporting.
- [`homesrvctl/state`](homesrvctl/state)
  SQLite state-store package for local cached stack state, observations, operations, events, schema initialization, and status helpers.
- [`homesrvctl/services`](homesrvctl/services)
  Reusable service layer for core operations shared by commands and future TUI/daemon/API surfaces.
- [`homesrvctl/services/daemon.py`](homesrvctl/services/daemon.py)
  Read-only foreground daemon service that periodically refreshes local observed state into SQLite.
- [`homesrvctl/services/daemon_systemd.py`](homesrvctl/services/daemon_systemd.py)
  Systemd unit rendering, installation, lifecycle action, log, and status helpers for the read-only daemon.
- [`homesrvctl/services/observers`](homesrvctl/services/observers)
  Read-only observer services for Docker Compose stack status, `cloudflared` runtime/config state, Traefik reachability, Cloudflare provider readiness, SES provider readiness, and observer persistence/status aggregation.
- [`homesrvctl/services/observers/cloudflare_provider.py`](homesrvctl/services/observers/cloudflare_provider.py)
  Read-only Cloudflare provider observer for token, zone, DNS, and tunnel readiness snapshots.
- [`homesrvctl/services/observers/ses_provider.py`](homesrvctl/services/observers/ses_provider.py)
  Read-only AWS SES provider observer for outbound mail, identity, DKIM, custom MAIL FROM, and DNS readiness snapshots.
- [`homesrvctl/adoption.py`](homesrvctl/adoption.py)
  Existing app/site source detection helpers used by adoption and wrapper command surfaces.
- [`homesrvctl/bootstrap.py`](homesrvctl/bootstrap.py)
  Fresh-host bootstrap assessment, final readiness aggregation, and tunnel/runtime/wiring provisioning helpers.
- [`homesrvctl/utils.py`](homesrvctl/utils.py)
  Shared filesystem and rendering helpers.
- [`homesrvctl/templates`](homesrvctl/templates)
  Template rendering utilities and shipped scaffold template assets.
- [`homesrvctl/template_catalog.py`](homesrvctl/template_catalog.py)
  Shipped scaffold catalog and rendered-template manifest definitions used by CLI scaffolds, wrapper templates, the TUI template picker, and packaging checks.
- [`homesrvctl/shell.py`](homesrvctl/shell.py)
  Shared subprocess execution helpers.
- [`homesrvctl/tui`](homesrvctl/tui)
  Terminal UI implementation. This is the home for the current Textual app and the JSON-backed data/action loading used by the TUI.
- [`homesrvctl/tui/app.py`](homesrvctl/tui/app.py)
  The current Textual app entrypoint for `homesrvctl tui`.
- [`homesrvctl/tui/data.py`](homesrvctl/tui/data.py)
  JSON-backed data loading, action dispatch, and detail rendering helpers for the Textual TUI.
- [`homesrvctl/tui/prompts.py`](homesrvctl/tui/prompts.py)
  Small Textual prompt screens used by guided TUI flows such as stack actions, tool menus, confirmations, and template selection.

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
- [`homesrvctl/commands/db_cmd.py`](homesrvctl/commands/db_cmd.py)
  Local SQLite state database commands such as `db init`, `db status`, and `db rebuild`.
- [`homesrvctl/commands/daemon_cmd.py`](homesrvctl/commands/daemon_cmd.py)
  Read-only daemon commands such as `daemon run`, `daemon install`, lifecycle actions, logs, and `daemon status`.
- [`homesrvctl/commands/observe_cmd.py`](homesrvctl/commands/observe_cmd.py)
  Read-only observer commands such as `observe run`, `observe run --cloudflare`, `observe run --ses`, and `observe status`.
- [`homesrvctl/commands/refresh_cmd.py`](homesrvctl/commands/refresh_cmd.py)
  Local refresh command that snapshots current stack directory state into the state database.
- [`homesrvctl/commands/install_cmd.py`](homesrvctl/commands/install_cmd.py)
  `version` and `install status` diagnostics for package version, executable path, and pipx command-path conflicts.
- [`homesrvctl/commands/bootstrap_cmd.py`](homesrvctl/commands/bootstrap_cmd.py)
  Fresh-host bootstrap assessment, readiness reporting, and tunnel/runtime/wiring provisioning command surface.
- [`homesrvctl/commands/site_cmd.py`](homesrvctl/commands/site_cmd.py)
  `site init` scaffold generation.
- [`homesrvctl/commands/app_cmd.py`](homesrvctl/commands/app_cmd.py)
  `app detect` source inspection, `app wrap` hosting wrapper generation, and `app init` scaffold generation for app templates.
- [`homesrvctl/commands/deploy_cmd.py`](homesrvctl/commands/deploy_cmd.py)
  Stack lifecycle commands such as `up`, `down`, `restart`, `list`, and `doctor`.
- [`homesrvctl/commands/domain_cmd.py`](homesrvctl/commands/domain_cmd.py)
  Domain lifecycle commands such as `add`, `status`, `repair`, and `remove`.
- [`homesrvctl/commands/ports_cmd.py`](homesrvctl/commands/ports_cmd.py)
  `ports list` inspection for ports discovered from rendered stack files.
- [`homesrvctl/commands/tunnel_cmd.py`](homesrvctl/commands/tunnel_cmd.py)
  Tunnel inspection command for configured tunnel resolution and Cloudflare API-backed tunnel status.
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
- [`homesrvctl/templates/app/rust-react-postgres`](homesrvctl/templates/app/rust-react-postgres)
  Rust API plus React/Vite frontend and internal Postgres scaffold.
- [`homesrvctl/templates/app/wrap`](homesrvctl/templates/app/wrap)
  Hosting wrapper templates for existing static directories and Dockerfile-based source trees.
- [`homesrvctl/templates/static`](homesrvctl/templates/static)
  Minimal `site init` scaffold assets.

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
