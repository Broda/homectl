# Changelog

All notable changes to `homesrvctl` should be recorded here.

This file is intentionally lightweight. It does not need to repeat every commit. It should capture user-facing changes, release-level milestones, and breaking or potentially surprising behavior changes.

The format is loosely based on Keep a Changelog, but kept simple for this project.

## Unreleased

### Added

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
- Broadened mixed-routing regression coverage for default stacks, profile-backed stacks, and direct override stacks.

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
