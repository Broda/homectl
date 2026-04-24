# Roadmap

`homesrvctl` is a small operator-focused CLI for managing self-hosted sites behind Cloudflare Tunnel, Traefik, and Docker Compose.

This roadmap now emphasizes current and upcoming work. Completed milestone detail is intentionally compressed so the file stays useful for deciding the next slice. Release-level history lives in [`CHANGELOG.md`](CHANGELOG.md), and architecture boundaries live in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Current Priorities

### 1. Release and Distribution Maturity

Status: ongoing

Goal: keep the project easy to ship, install, and verify as the public surface grows.

Near-term work:
- Prepare follow-up releases from focused changelog sections as new operator-facing slices land.
- Keep tagged release automation, local build verification, and [`RELEASING.md`](RELEASING.md) aligned.
- Keep package metadata, README install guidance, and release artifacts accurate.
- Decide whether GitHub-generated release notes remain enough or whether a small curated release-note template is worthwhile.

Success criteria:
- `python -m build` remains reproducible locally.
- CI and release workflows exercise the same core checks.
- Version, changelog, and release tag expectations are explicit and low-friction.

### 2. TUI Operator-Facing Polish

Status: complete

Goal: make the Textual dashboard read like an operator tool rather than raw command output.

Current baseline:
- The TUI is functionally complete for common local onboarding.
- It can create stacks, onboard apex domains, inspect routing/domain state, run stack actions, and expose global tools.
- Recent polish replaced several raw boolean values and normalized `yes/no`, `N/A`, and `exists/does not exist` wording across visible detail panes.
- Repeated checks and command results use rounded Unicode table-style layouts where scanning across repeated rows matters.
- DNS records and ingress routes use stacked key/value record blocks so long hostnames, tunnel targets, and ancillary records do not wrap through table borders.
- Single-value sections keep compact key/value rows, and long free-form repair guidance remains list-oriented so commands stay readable.

Success criteria:
- The dashboard remains compact but uses operator-facing labels consistently. Met.
- Copy changes do not alter CLI command semantics or JSON contracts. Met.

### 3. Scaffold Surface Consolidation

Status: planned

Goal: decide whether the current scaffold catalog should stay app-template-only or grow into a broader registry.

Current baseline:
- App template names, descriptions, rendered file manifests, TUI template choices, and packaging checks are driven by `homesrvctl/template_catalog.py`.
- `site init` and `app init --template static` intentionally remain separate public surfaces:
  - `site init` is the narrow two-file static scaffold.
  - `app init --template static` is the richer nginx-backed static app scaffold.

Near-term work:
- Evaluate whether adding `site init` metadata to the shared catalog would reduce maintenance.
- Keep public command surfaces stable unless a concrete simplification justifies a change.
- Preserve the documented distinction between `site init` and `app init --template static`.

Success criteria:
- Scaffold registration, docs, TUI choices, and packaging checks do not drift.
- Any registry expansion simplifies maintenance without broadening product scope.

### 4. Cloudflare Control-Plane Extensions

Status: planned

Goal: add narrow Cloudflare-adjacent inspection and convergence features that directly improve self-hosted app operations.

Preferred ordering:
1. Domain onboarding and delegation checks.
2. Richer tunnel API inspection and remote config visibility.
3. Ancillary DNS and Email Routing visibility.
4. Access protection for private services.
5. Zone edge setting profiles.
6. Redirect and edge-rule profiles.

Design constraints:
- Keep the shared-host-tunnel and local-Traefik model intact.
- Start read-focused before adding mutation verbs.
- Avoid becoming a broad Cloudflare administration console.
- Surface normalized operator-facing state instead of raw Cloudflare payloads.

Success criteria:
- Operators can identify Cloudflare-side blockers before domain mutation attempts.
- New Cloudflare features remain narrow, explicit, and convergent.

### 5. Existing App Adoption and Hosting Wrappers

Status: proposed

Goal: help operators bring existing apps into the `homesrvctl` hosting model without adding a long tail of framework-specific templates.

Why this is high-value:
- Many operators already have application repos.
- `homesrvctl` is strongest when it generates hosting wrappers:
  - Compose wiring
  - Traefik labels
  - stack-local config
  - operator README guidance

Suggested phases:
- Phase 1: add inspect-only source detection. Shipped after `0.4.0`.
  - Candidate command: `homesrvctl app detect <source_path> [--json]`
  - Detect advisory families such as `static`, `node`, `python`, `jekyll`, `dockerfile`, or `unknown`.
  - Report evidence, confidence, issues, and next steps.
- Phase 2: generate hosting wrappers around existing source.
  - Candidate command: `homesrvctl app wrap <hostname> --source <source_path> [--family FAMILY] [--force] [--json]`
  - Generate wrapper-owned files only.
  - Avoid modifying app-owned source in v1.
- Phase 3: add a full adoption flow only after wrapper ownership rules are stable.
  - Candidate command: `homesrvctl app adopt <hostname> --source <source_path> [--family FAMILY] [--force] [--json]`
- Phase 4: expose detection and wrapper flows in the TUI through the existing JSON-backed action pattern.

Design constraints:
- Detection stays advisory, not magical.
- Generated output remains small and hosting-focused.
- External path coupling should not become the default operator model.

Success criteria:
- Operators can host an existing app without manually recreating Compose and Traefik wiring.
- Failure modes stay concrete and repairable.

### 6. Mail Provider and Routing Surfaces

Status: proposed

Goal: add mail-related domain administration only where it fits the same narrow operator model as DNS and tunnel readiness.

Candidate areas:
- SES outbound readiness inspection and narrow identity convergence.
- Cloudflare Email Routing inspection and explicit route administration.

Suggested sequencing:
- Keep SES and Cloudflare Email Routing as separate provider implementations.
- Start inspect-only:
  - account/provider readiness
  - domain identity state
  - required DNS records
  - operator-facing issues and next steps
- Add mutation commands only after JSON output and read behavior stabilize.
- Add TUI views only after CLI contracts exist.

Design constraints:
- Do not turn `homesrvctl` into a general mail platform, cloud console, or application mailer.
- Do not fold provider logic into `homesrvctl/cloudflare.py` as unrelated one-off behavior.
- Keep per-app mail runtime wiring separate from domain/admin inspection.

Success criteria:
- Operators can distinguish account-state, identity-state, and DNS-state blockers.
- Provider output is normalized and readable.

## Completed Baseline

The following areas are shipped and considered the current baseline.

### Core CLI and Public Contracts

- Config initialization and inspection.
- Stack scaffolding through `site init` and `app init`.
- Deploy lifecycle through `up`, `down`, `restart`, `list`, `doctor`, and `validate`.
- JSON output across the public CLI surface with a shared top-level `schema_version`.
- Public contract discipline for CLI names, major flags, JSON shapes, config formats, stack-local config, and documented scaffold output.

### Domain and Routing

- Domain lifecycle commands:
  - `domain add`
  - `domain status`
  - `domain repair`
  - `domain remove`
- API-based Cloudflare DNS management.
- Local `cloudflared` ingress reconciliation.
- Domain diagnostics for missing, wrong, duplicate, shadowed, partial, and ambiguous DNS/ingress states.
- Routing profiles and stack-local overrides:
  - global defaults
  - named `profiles`
  - stack-local `profile`
  - direct stack-local `docker_network` and `traefik_url`

### Cloudflared Operations and Setup Safety

- Runtime detection for systemd, Docker-managed, and unmanaged process modes.
- `cloudflared status`, `setup`, `restart`, `reload`, `logs`, and `config-test`.
- Normalized blocking versus advisory ingress issue severity.
- Shared-group setup guidance for `/srv/homesrvctl/cloudflared`.
- Early failure for domain mutations when local ingress mutation would be unsafe.

### Bootstrap

- Explicit fresh-host bootstrap slices for Debian-family Raspberry Pi targets:
  - `bootstrap assess`
  - `bootstrap tunnel`
  - `bootstrap runtime`
  - `bootstrap wiring`
  - `bootstrap validate`
- One shared host tunnel.
- Traefik retained as the local ingress router.
- API-token-first Cloudflare provisioning.
- No single unattended installer by design.

### Terminal UI

- Textual is the only retained `homesrvctl tui` implementation.
- Running bare `homesrvctl` launches the dashboard.
- The TUI uses existing JSON command surfaces instead of a separate backend.
- Supported flows include:
  - stack inspection and actions
  - stack creation
  - apex domain onboarding
  - config, tunnel, bootstrap, validation, and cloudflared tool panes
  - keyboard and additive mouse interaction

### Templates and Port Inspection

- Shipped app templates:
  - `placeholder`
  - `node`
  - `python`
  - `static`
  - `static-api`
  - `jekyll`
  - `rust-react-postgres`
- Template-aware port overrides through `app init --port NAME=PORT`.
- `ports list` for rendered stack port discovery.
- Scaffold catalog and release packaging checks cover shipped template assets.

### Release Infrastructure

- CI is in place for Python 3.11 and 3.12.
- Tagged releases build artifacts and publish through TestPyPI, PyPI, and GitHub Releases.
- Release packaging tests verify version alignment and shipped template assets.

## Cross-Cutting Rules

- Prefer small, end-to-end slices.
- Prefer idempotent mutation behavior.
- Keep command modules as orchestrators over lower-level helpers.
- Preserve public contracts deliberately.
- Add regression tests when commands gain runtime branches, output modes, mutation side effects, or JSON fields.
- Update README, changelog, roadmap, architecture, file map, and wiki docs when their owned surface changes.
