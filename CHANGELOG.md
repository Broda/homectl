# Changelog

All notable changes to `homesrvctl` should be recorded here.

This file is intentionally lightweight. It does not need to repeat every commit. It should capture user-facing changes, release-level milestones, and breaking or potentially surprising behavior changes.

The format is loosely based on Keep a Changelog, but kept simple for this project.

## Unreleased

### Fixed
- Keep `--json` status and validation output free of probe noise so the terminal dashboard can consume `cloudflared status`, `validate`, and `doctor` reliably.
- Tightened `domain status` diagnostics so DNS and ingress conflicts now distinguish missing records, wrong types, wrong targets, duplicate ingress entries, shadowing, and manual-cleanup cases more explicitly.
- Normalized `cloudflared` ingress issue severity so blocking semantic-danger states now fail health checks while broader wildcard-precedence risks remain advisory.
- Refreshed the roadmap and repo docs so milestone status and current TUI/template baselines match the shipped implementation more closely.
- Removed the dead curses dashboard module and its obsolete tests now that `homesrvctl tui` is fully on the Textual path.

### Added

- Added a shared scaffold catalog module so app-template names, descriptions, rendered file manifests, TUI template choices, and release packaging checks now come from one source of truth.
- Added parity-style artifact-coherence coverage for the shipped `site init`, `static`, `static-api`, and `placeholder` scaffold families so template manifests, compose wiring, and operator guidance stay aligned.
- Added release-oriented regression coverage that builds fresh wheel and sdist artifacts and verifies the full shipped template asset catalog is present in both distributions.
- Added a first `jekyll` app template that builds a stack-local Jekyll site into an nginx-served image for manual adoption of an existing Jekyll repo.
- Added Textual as the new TUI dependency and introduced a first Textual app foundation behind `homesrvctl tui`.
- Added a first read-only `homesrvctl tui` dashboard that reuses the existing JSON command surface for stack, `cloudflared`, and validation summaries.
- Expanded the initial TUI dashboard with keyboard selection, a focused detail pane, and a footer that shows controls plus refresh mode.
- Added first stack controls to the TUI so the selected hostname can run `doctor`, `up`, `restart`, and `down` directly from the dashboard.
- Added `site init` as a TUI stack action so an empty hostname can be scaffolded directly from the dashboard.
- Added cached stack-action detail in the Textual TUI so the focused stack pane now shows the last `doctor`, `site init`, `up`, `restart`, or `down` result instead of only a footer status line.
- Added first `Cloudflared` tool actions to the Textual TUI so the focused tool pane can run `config-test`, `reload`, and `restart` and keep the last result visible in the detail pane.
- Added a first guided scaffold flow to the Textual TUI: focused stacks can now open an `app init` template picker and run the selected scaffold without leaving the dashboard.
- Added `config show` coverage to the Textual TUI via a new global `Config` tool item plus effective per-stack config detail in the focused stack pane.
- Added `domain status` coverage to the Textual TUI for apex stacks so the focused stack pane now surfaces domain-level DNS and ingress status, repairability, and suggested remediation.
- Added apex-only `domain repair` as a stack action in the Textual TUI so an operator can act on the surfaced repairability signal without leaving the dashboard.
- Added apex-only confirmed `domain add` and `domain remove` actions to the Textual TUI so domain onboarding and teardown can be launched from the focused stack pane without leaving the dashboard.
- Added a guided stack action menu to the Textual TUI so focused stacks expose their stack-local and apex-domain actions through a discoverable modal in addition to the direct hotkeys.
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
- Broadened routing regression coverage for scaffold flows so `site init` and `app init` now cover profile selection, one-off `traefik_url` overrides, and combined override cases more explicitly.
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

### Changed

- Broadened release-packaging verification from Jekyll-only coverage to the full shipped template asset catalog.
- Added a root `.dockerignore` to the `static-api` scaffold so its stack-root Python image build follows the same build-context convention as the other image-building app templates.
- Tightened the generated Jekyll scaffold guidance so adoption instructions now spell out which root-level stack files to keep, which `site/` contents to replace, how the adopted source tree should sit under `site/`, and when native gem dependencies require Dockerfile edits.
- Expanded Jekyll scaffold regression coverage to lock down compose labels, healthcheck behavior, build flow assumptions, starter files, and stack-local routing override output.
- Reworked the Textual dashboard layout into a roomy warm-console design with a top summary strip, a unified left control pane, a right operational detail pane, and a persistent command/status bar.
- Replaced the old section-plus-stack split navigation model in the Textual dashboard with a single vertical control cursor through `Tools` and `Stacks`.
- Clarified the routing-profile model in the docs: top-level routing keys are the implicit default profile, stacks opt in with `profile`, and direct stack-local overrides remain first-class and win last.
- Updated `cloudflared status`, `cloudflared config-test`, `validate`, `doctor`, `domain status`, and the TUI to expose normalized ingress issue severity in JSON and operator-facing detail views.

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
