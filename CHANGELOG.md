# Changelog

All notable changes to `homesrvctl` should be recorded here.

This file is intentionally lightweight. It does not need to repeat every commit. It should capture user-facing changes, release-level milestones, and breaking or potentially surprising behavior changes.

The format is loosely based on Keep a Changelog, but kept simple for this project.

## Unreleased

### Added
- Added `homesrvctl cleanup HOST` to stop a stack with Docker Compose and delete its local stack directory after `--force`, with dry-run, JSON, and TUI confirmation support.
- Added a non-root full-pipeline operator model after one-time bootstrap: shared cloudflared directories are now operator-group writable, `bootstrap wiring` installs a scoped cloudflared restart/reload sudoers policy, and setup reports now surface group/session and service-control readiness.
- Added `homesrvctl ports list` to report the ports discovered from rendered stack files, including compose environment defaults, Traefik service ports, healthchecks, Dockerfile `EXPOSE`, and fixed Postgres command wiring.
- Added template-aware `app init --port NAME=PORT` overrides for configurable scaffold ports so generated compose files, runtime defaults, healthchecks, Dockerfiles, and README guidance no longer have to stay pinned to the same repeated internal port values.
- Added a `rust-react-postgres` app template that scaffolds a Raspberry Pi-friendly three-service stack with a React/Vite frontend served by nginx, an internal Rust API with `/healthz`, and stack-private Postgres behind the existing Cloudflare Tunnel plus Traefik model.
- Running `homesrvctl` with no arguments now launches the Textual dashboard by default, matching `homesrvctl tui`.
- Added `homesrvctl bootstrap assess` as the first fresh-host bootstrap slice. It is assessment-only and reports whether the current host looks `fresh`, `partial`, `ready`, or `unsupported` relative to the first Debian-family Raspberry Pi bootstrap target.
- Added `homesrvctl bootstrap runtime` as the host-baseline bootstrap slice. It supports `--dry-run` and `--json`, installs Docker Engine plus the Docker Compose plugin and `cloudflared`, creates the shared `homesrvctl` group and `/srv/homesrvctl` directory layout, creates the external Docker network, and writes plus starts the baseline Traefik runtime.
- Added `homesrvctl bootstrap tunnel` as the first mutating bootstrap slice. It can create a locally managed Cloudflare tunnel through the API, reuse an existing tunnel only when matching local credentials are already available, write bootstrap tunnel credentials plus a minimal local `cloudflared` config, and normalize the main config tunnel reference to the resolved UUID.
- Added `homesrvctl bootstrap wiring` as the shared-group cloudflared convergence slice. It supports `--dry-run` and `--json`, creates the main config when missing, normalizes `cloudflared_config` to `/srv/homesrvctl/cloudflared/config.yml`, migrates tunnel credentials into the shared directory, writes the shared config, installs the required systemd unit or override, and enables the `cloudflared` service.
- Added `homesrvctl bootstrap validate` as the final shipped bootstrap-readiness command. It supports `--json` and composes bootstrap assessment, host validation, tunnel resolution, and shared-group `cloudflared` setup readiness into one explicit `ready`, `not_ready`, or `unsupported` result.
- Added `cloudflared setup` to assess whether the configured `cloudflared` config path is writable and aligned with the active runtime, and to print exact systemd override / migration commands when setup repair is needed.
- Added setup-alignment reporting to `cloudflared status` plus a matching `Fix Setup` action in the TUI `Cloudflared` pane.
- Added a global TUI stack-creation flow that can scaffold a new hostname through the existing `site init` and `app init` commands without requiring a pre-existing stack row.
- Added sequential TUI prompts for new-stack hostname entry, create-mode selection, optional app-template selection, and optional routing overrides (`profile`, `docker_network`, `traefik_url`).
- Added TUI overwrite confirmation for scaffold creation when the underlying CLI reports that generated files already exist.
- Defined the current “fully functional” TUI creation contract for common local onboarding, including what remains intentionally CLI-only and which broader creation/editing workflows stay out of scope.
- Added `homesrvctl tunnel status` to report the configured tunnel reference, resolved tunnel UUID, resolution source, and Cloudflare API tunnel status when account-scoped tunnel inspection is available.
- Added `Tunnel` as a first-class TUI tool item so `homesrvctl tui` can inspect the current `tunnel status` output and rerun tunnel inspection from the guided tool menu.
- Added shared-group `cloudflared` setup guidance so `cloudflared status` and `cloudflared setup` now report tunnel-credentials readability, account-inspection availability, service user/group context, and exact systemd migration commands for the supported `root:homesrvctl` `/srv/homesrvctl/cloudflared` layout.
- Added direct regression coverage for `inspect_cloudflared_setup` so partial-versus-ready credential access states stay stable.
- Added roadmap and documentation direction for a future fresh-Pi bootstrap workflow targeting Debian-family Raspberry Pi hosts, one shared host tunnel, Traefik retention, and API-token-first Cloudflare provisioning.
- Added `Bootstrap` as a first-class TUI tool and summary card so the dashboard now surfaces `bootstrap assess` host-readiness state, issues, and next-step guidance alongside the existing config, tunnel, cloudflared, and validation views.
- TUI mouse support: the control pane rows, summary cards, modal option lists, confirm prompts, and a new detail-pane action button strip are now real Textual widgets that respond to clicks. Mouse and keyboard selection share the same highlighted row, every click target is also reachable by keyboard, and clicks are quietly ignored on terminals that do not report mouse events.
- TUI visual polish: status ok / warning / error values, PASS/FAIL/WARN check markers, domain overall status, DNS/ingress match state, and cloudflared active/inactive are now color-coded via Rich markup; detail section headers use the accent color; the detail pane title updates to reflect the focused stack or tool; and per-pane help prose was replaced with a single compact hint line.
- TUI detail-pane polish: stack and domain detail views now use more operator-facing wording such as `compose file: exists`, `has local config: yes/no`, and `repairable: N/A/Yes/No`, and the domain pane now renders DNS and ingress rows in bordered table layouts for faster scanning.

### Fixed
- Changed the default tunnel ingress target to `http://localhost:80` so new bootstrap configs route Cloudflare Tunnel traffic to Traefik's public web entrypoint instead of the Traefik dashboard/API port on `8081`.
- Added diagnostics for cloudflared ingress routes that point at the bootstrap Traefik dashboard/API port, so `domain status`, `doctor`, validation output, and the TUI can surface the misrouting.
- Fixed `bootstrap runtime` on Ubuntu-family hosts such as Ubuntu 24.04 `noble` so Docker apt sources use Docker's Ubuntu repository instead of incorrectly writing a Debian repository entry.
- The TUI apex-domain `Create` flow now preserves the underlying `domain add` failure detail in its status message instead of stopping at a generic `domain add failed`.
- Bare-domain scaffolds now render Traefik host rules for both the apex hostname and `www.<domain>`, so wildcard tunnel traffic for `www` no longer falls through to Traefik's default 404 on freshly scaffolded apex stacks.
- `domain status` and the TUI stack pane now warn when an explicit `www.<domain>` DNS record overrides the wildcard tunnel route, which catches common legacy-hosting leftovers that apex-plus-wildcard checks alone would miss.
- TUI apex-domain mutations now request `--restart-cloudflared` by default so guided `domain add`, `domain repair`, `domain remove`, and apex `Create` flows apply ingress changes to the running service instead of only rewriting the config file on disk.
- TUI stack action detail now surfaces the domain-mutation apply step explicitly, including restart success/failure and the restart command when available.
- The TUI detail panes no longer show inline command-hint footer text; shortcut keys now appear directly in the detail-button labels instead.
- The TUI cloudflared detail pane now trims the redundant trailing `OK` line from config-validation detail text.
- Changed the shared-group `cloudflared` config guidance and bootstrap wiring permissions so `/srv/homesrvctl/cloudflared/config.yml` is now group-writable for trusted operators, while the tunnel credentials JSON remains non-public.
- `cloudflared status`, `cloudflared setup`, and `bootstrap validate` now handle unreadable runtime/config paths as clean setup failures instead of crashing with a Python traceback.
- Updated `bootstrap wiring` next-step guidance so it now points at the shipped `homesrvctl bootstrap validate` command instead of the old pre-release placeholder text.
- Changed the first-class `cloudflared` operator model to use a dedicated `homesrvctl` group for secret tunnel credentials instead of recommending user-owned writable config files.
- Changed `cloudflared setup` to generate shared-group migration commands and a systemd override that sets `Group=homesrvctl`.
- Changed `tunnel status` and the TUI tunnel pane to describe unreadable local credentials as an account-inspection limitation, with setup guidance, instead of surfacing a raw permission failure.
- `domain add`, `domain repair`, and `domain remove` now fail before DNS changes when the configured `cloudflared` ingress file cannot actually be mutated from the current setup, avoiding partial DNS-only updates when the active systemd service points at a different config file or the configured path is not writable.
- `domain add`, `domain repair`, and `domain remove` now surface `cloudflared` config write failures as operator-facing errors with remediation hints instead of raw Python tracebacks when the configured ingress file is not writable.
- Keep `--json` status and validation output free of probe noise so the terminal dashboard can consume `cloudflared status`, `validate`, and `doctor` reliably.
- Tightened `domain status` diagnostics so DNS and ingress conflicts now distinguish missing records, wrong types, wrong targets, duplicate ingress entries, shadowing, and manual-cleanup cases more explicitly.
- Normalized `cloudflared` ingress issue severity so blocking semantic-danger states now fail health checks while broader wildcard-precedence risks remain advisory.
- Changed the TUI `Create` flow so apex hostnames now auto-run `domain add` before scaffold creation, while subdomain creation remains scaffold-only and the standalone top-level TUI domain-onboarding entrypoint is no longer exposed.
- Reduced domain tunnel-target lookup dependence on local `cloudflared tunnel info` by resolving the tunnel UUID through the Cloudflare API when local UUID sources are unavailable.
- Reduced `validate` tunnel-reference dependence on local `cloudflared tunnel info` by resolving the configured tunnel through the Cloudflare API when the local `cloudflared` config includes tunnel credentials context.
- Removed the remaining `cloudflared tunnel info` fallback from tunnel inspection helpers so tunnel resolution now stays explicit: local UUID sources first, then account-scoped API lookup when credentials context exists.
- Tightened packaging/version drift checks by deriving runtime HTTP user-agent strings from the package version and adding regression coverage that `homesrvctl.__version__` matches `pyproject.toml`.
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
- Added guided global tool menus to the Textual TUI so focused `Config` and `Cloudflared` items can launch `config init`, `cloudflared logs`, and other low-frequency tool actions without leaving the dashboard.
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
- New starter configs now default `cloudflared_config` to `/srv/homesrvctl/cloudflared/config.yml`; existing installs keep honoring their already-configured path without automatic migration.
- Bootstrap ready-state copy now says the host is ready for `stack operations and domain onboarding`, instead of implying only first-time stack creation.
- Broadened release-packaging verification from Jekyll-only coverage to the full shipped template asset catalog.
- Added a root `.dockerignore` to the `static-api` scaffold so its stack-root Python image build follows the same build-context convention as the other image-building app templates.
- Tightened the generated Jekyll scaffold guidance so adoption instructions now spell out which root-level stack files to keep, which `site/` contents to replace, how the adopted source tree should sit under `site/`, and when native gem dependencies require Dockerfile edits.
- Expanded Jekyll scaffold regression coverage to lock down compose labels, healthcheck behavior, build flow assumptions, starter files, and stack-local routing override output.
- Reworked the Textual dashboard layout into a roomy warm-console design with a top summary strip, a unified left control pane, a right operational detail pane, and a persistent command/status bar.
- Replaced the old section-plus-stack split navigation model in the Textual dashboard with a single vertical control cursor through `Tools` and `Stacks`.
- Extended the Textual TUI so `cloudflared logs` guidance and default-path `config init` results now stay explorable in the focused tool detail pane, closing the remaining Milestone 5 command-coverage gaps.
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
