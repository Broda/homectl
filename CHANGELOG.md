# Changelog

All notable changes to `homesrvctl` should be recorded here.

This file is intentionally lightweight. It does not need to repeat every commit. It should capture user-facing changes, release-level milestones, and breaking or potentially surprising behavior changes.

The format is loosely based on Keep a Changelog, but kept simple for this project.

## Unreleased

### Added

- Added a first read-only `homesrvctl tui` dashboard that reuses the existing JSON command surface for stack, `cloudflared`, and validation summaries.
- Expanded the initial TUI dashboard with keyboard selection, a focused detail pane, and a footer that shows controls plus refresh mode.
- Added [`FILE_MAP.md`](FILE_MAP.md) as a repository orientation guide.
- Reorganized [`ROADMAP.md`](ROADMAP.md) into milestone-based planning with tasks and subtasks.
- Added `config show` with text and JSON output for global config inspection and effective stack-local override inspection.
- Added named routing profiles in global config plus stack-local `profile` selection for scaffolded stacks.
- Added routing-context reporting to `domain status`, including default versus effective ingress target and source attribution.
- Added routing-context reporting to `doctor`, including routing profile plus default and effective ingress targets.
- Added non-fatal `cloudflared` ingress warning reporting for risky wildcard shadowing in `cloudflared status` and `cloudflared config-test`.
- Added the same non-fatal ingress shadowing warnings to `domain status` and `doctor`.
- Added `cloudflared reload` for runtimes that expose a safe reload command.
- Broadened `cloudflared` ingress warning detection to cover broad wildcard rules that may capture traffic intended for a narrower wildcard.
- Made non-fatal `cloudflared` ingress warnings more remediation-oriented by embedding direct fix hints in the surfaced messages.
- Made `cloudflared status` explicit about warning policy: structurally valid ingress warnings remain advisory and do not flip the status command to failure while the runtime is healthy.
- Broadened mixed-routing regression coverage for default stacks, profile-backed stacks, and direct override stacks.
- Added basic healthchecks to the generated `node` and `python` app templates so scaffolded containers verify their default root endpoints.
- Added dedicated `/healthz` endpoints to the generated `node` and `python` apps so healthchecks no longer probe the user-facing root response.
- Tightened generated Dockerfile defaults so the Node scaffold installs runtime dependencies and the Python scaffold sets standard runtime environment flags before installing requirements.
- Standardized the generated app runtime baseline so both `node` and `python` scaffolds document `GET /` plus `GET /healthz`, expose their runtime inputs clearly, and return explicit `405` responses for unsupported methods.
- Removed unused metadata-style keys from the generated `node` and `python` `.env.example` files so they now only document real runtime overrides.
- Turned `app init --template static` into a real static-site scaffold with nginx, `html/index.html`, a generated README, and a container healthcheck.
- Expanded the static-site scaffold to include starter asset folders plus placeholder `main.css` and `main.js` files wired from `index.html`.
- Added a placeholder `favicon.svg` to the static-site scaffold and wired it from the generated HTML.
- Added a first `static-api` app template that combines a static nginx site with a small Python API routed on `/api`.
- Expanded scaffold regression coverage so generated `node` and `python` artifacts stay consistent across ports, healthchecks, first-run docs, and rendered template manifests.

## 0.2.0 - 2026-04-08

### Added

- Added full domain lifecycle support:
  - `domain add`
  - `domain status`
  - `domain repair`
  - `domain remove`
- Added API-based Cloudflare DNS management for domain onboarding.
- Added `cloudflared` ingress reconciliation to domain mutation flows.
- Added `cloudflared` runtime commands:
  - `status`
  - `restart`
  - `logs`
  - `config-test`
- Added JSON output across the main CLI surface, including scaffold, deploy, domain, validation, and `cloudflared` commands.
- Added a shared JSON `schema_version`.
- Added multi-file `node` and `python` app templates.
- Added stack-local `homesrvctl.yml` overrides for `docker_network` and `traefik_url`.
- Added automated tagged releases with artifact builds, TestPyPI publishing, PyPI publishing, and GitHub Releases.
- Added the project wiki and linked it from the README.

### Changed

- Renamed the project and package from `homectl` to `homesrvctl`.
- Switched public install guidance to prefer PyPI.
- Reorganized the roadmap into milestone-based planning.

### Fixed

- Fixed release workflow issues around checkout and publish sequencing.
- Fixed CI packaging metadata compatibility with current `setuptools`.

## 0.1.0 - 2026-04-08

### Added

- First public tagged release.
- Initial GitHub release automation.
- Initial public documentation, CI, and packaging baseline.
