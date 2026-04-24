# Architecture

This document describes the current structure of `homesrvctl`, the boundaries between major modules, and the public contracts that should not drift casually.

## Design Goals

- Keep the operator model simple and explicit.
- Prefer convergent, idempotent mutation commands.
- Keep external-system integrations isolated from command wiring.
- Preserve stable public contracts where practical.
- Grow the project in small slices rather than speculative abstraction.

## Major Components

### CLI surface

- [`homesrvctl/main.py`](homesrvctl/main.py)
- [`homesrvctl/commands`](homesrvctl/commands)

Responsibilities:
- define the user-facing command tree
- parse flags and arguments
- format human-readable and JSON output
- orchestrate lower-level helpers
- host the terminal UI entrypoint

Should not do:
- embed Cloudflare request details directly
- embed `cloudflared` config parsing logic directly
- spread shell/process logic across individual commands

### Config and model layer

- [`homesrvctl/models.py`](homesrvctl/models.py)
- [`homesrvctl/config.py`](homesrvctl/config.py)
- [`homesrvctl/ports.py`](homesrvctl/ports.py)

Responsibilities:
- define global config structure
- define stack-local config structure
- resolve config paths and defaults
- load effective stack-local overrides
- inspect rendered stack files for service-port usage when operator reporting needs that view

This is the source of truth for:
- global config shape
- stack-local `homesrvctl.yml` shape
- default path conventions

### Cloudflare integration

- [`homesrvctl/cloudflare.py`](homesrvctl/cloudflare.py)

Responsibilities:
- Cloudflare DNS API interactions
- zone lookup
- DNS record inspection, upsert, and removal
- tunnel-target-related helper logic used by domain and tunnel-inspection flows

This module should stay focused on Cloudflare control-plane behavior, not local runtime orchestration.

Future note:
- If mail-provider admin support is introduced, it should not be added to `cloudflare.py` or folded into existing domain command wiring as ad hoc boto or SMTP calls.
- The frontend surface may use a generic `mail` command family, but provider logic should remain provider-specific.
- A future generic `mail` command surface may accept `--provider`, but the default should stay `ses` until another provider is actually shipped.
- A future layout such as:
  - [`homesrvctl/mail_models.py`](homesrvctl/mail_models.py)
  - [`homesrvctl/mail_providers/ses.py`](homesrvctl/mail_providers/ses.py)
  can provide normalized output models plus provider-specific implementations without forcing a fake universal SMTP abstraction.
- Shared mail models should normalize only the parts that genuinely generalize:
  - provider name
  - domain/account inspection status
  - DNS record readiness
  - repairability
  - operator-facing issues and next steps
- Provider-specific detail such as SES DKIM state, custom MAIL FROM state, or account sandbox status should remain in provider-owned logic and may surface under explicit `provider_detail` output fields.

### Cloudflared ingress and runtime integration

- [`homesrvctl/cloudflared.py`](homesrvctl/cloudflared.py)
- [`homesrvctl/cloudflared_service.py`](homesrvctl/cloudflared_service.py)

Responsibilities:
- parse and validate `cloudflared` ingress config
- reconcile ingress entries for domain lifecycle commands
- detect `cloudflared` runtime mode
- inspect whether the configured `cloudflared` path is aligned with the active runtime
- inspect whether the current user can read the configured tunnel credentials JSON
- generate systemd-oriented setup guidance for the supported shared-group `root:homesrvctl` layout when the runtime, config path, service-control policy, or credentials access diverge
- support a one-time privileged bootstrap boundary where normal stack/domain/TUI operations later run as a trusted non-root operator in the `homesrvctl` and `docker` groups
- select restart/log commands appropriate for the detected runtime

Keep a clear separation between:
- config-file semantics
- runtime/process management

### Scaffold and template layer

- [`homesrvctl/templates.py`](homesrvctl/templates.py)
- [`homesrvctl/template_catalog.py`](homesrvctl/template_catalog.py)
- [`homesrvctl/adoption.py`](homesrvctl/adoption.py)
- [`homesrvctl/templates/static`](homesrvctl/templates/static)
- [`homesrvctl/templates/app`](homesrvctl/templates/app)

Responsibilities:
- render scaffold templates
- define the shipped scaffold catalog for commands, TUI flows, and release verification
- inspect existing app/site source directories before wrapper/adoption flows mutate anything
- keep template families organized
- support site and app initialization without making `homesrvctl` a general-purpose framework generator

The per-template directory layout under `templates/app/` is intentional and should be preserved.
The scaffold catalog should stay as the source of truth for shipped app-template names, operator-facing descriptions, and rendered file manifests.
`site init` remains a separate minimal scaffold family from `app init --template static`; that split is intentional until a later design decision says otherwise.
Scaffold scope should stay within the philosophy recorded in [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md): small deployable baselines, not framework stacks.
Existing-app adoption should start read-only and report evidence, confidence, issues, and concrete next steps before any wrapper files are generated.

### Shared utilities

- [`homesrvctl/shell.py`](homesrvctl/shell.py)
- [`homesrvctl/utils.py`](homesrvctl/utils.py)

Responsibilities:
- common shell execution behavior
- filesystem helpers
- shared small utilities used by command modules

These helpers should stay generic and reusable rather than accumulating feature-specific logic.

### Bootstrap assessment

- [`homesrvctl/bootstrap.py`](homesrvctl/bootstrap.py)
- [`homesrvctl/commands/bootstrap_cmd.py`](homesrvctl/commands/bootstrap_cmd.py)

Responsibilities:
- assess fresh-host readiness for the planned Debian-family bootstrap target
- provision the shared Cloudflare tunnel and local bootstrap material for later host/runtime wiring
- converge the host runtime baseline for the first bootstrap target, including packages, shared directories/groups, Docker network, and baseline Traefik runtime
- converge the shared-group `cloudflared` config path, tunnel credentials layout, and systemd service wiring
- aggregate the completed bootstrap slices into one explicit final host-readiness result
- detect current host/package/runtime/config/token state without mutating the host
- keep bootstrap orchestration separate from the existing domain, stack, and runtime command modules

The current shipped slices cover assessment, Cloudflare tunnel provisioning plus local bootstrap material writing, host runtime baseline convergence, shared-group cloudflared wiring, and a final bootstrap-readiness aggregation step.
Future bootstrap mutation flows should continue building on this layer rather than spreading provisioning logic across unrelated modules.

## Current Architectural Boundaries

### Commands should orchestrate, not reimplement helpers

Command modules may decide:
- what action to run
- which helper to call
- how to present the result

Command modules should avoid:
- custom YAML parsing when `cloudflared.py` already owns it
- ad hoc Cloudflare API requests
- ad hoc subprocess behavior already covered by `shell.py`

The TUI command wrapper follows the same rule: it should prefer orchestrating stable JSON command output over reaching into unrelated modules directly unless that boundary becomes a maintenance problem.

### Terminal UI layer

- [`homesrvctl/tui`](homesrvctl/tui)

Responsibilities:
- host the Textual application and related screens/widgets
- load dashboard and action data from the existing JSON command surface
- render terminal dashboard views, detail panes, and guided flows
- manage TUI-local selection and detail state
- keep TUI-specific state and refresh behavior out of the command modules

This layer should stay separate from CLI wiring so future dashboard/view growth does not bloat `homesrvctl/commands`.
Textual is now the active and only retained implementation for `homesrvctl tui`.
The command wrapper should import the Textual app lazily so the rest of the CLI can still start cleanly if the local environment has not yet been refreshed to include the new dependency.
The shipped TUI now covers the public CLI surface with a mix of guided mutation flows, focused tool menus, and read-only detail views instead of relying on a separate backend model.
The TUI is mouse-aware: control rows, summary cards, modal option rows, confirm-prompt buttons, and the detail-pane action button strip are real Textual widgets that accept both keyboard and mouse input. Mouse and keyboard selection share a single `--selected` class on the same row widget, so the two input modes cannot drift into separate tracks; click targets are additive rather than replacements for the underlying keyboard bindings.

### Public contract changes should be deliberate

The following are public contracts for this project:

- CLI command names and major flags
- JSON output shapes
- global config file format
- stack-local `homesrvctl.yml` format
- generated scaffold file layout where it is documented

These can change, but they should not drift accidentally. User-visible changes should be reflected in:
- [`CHANGELOG.md`](CHANGELOG.md)
- [`README.md`](README.md) when appropriate
- [`ROADMAP.md`](ROADMAP.md) when scope or direction changes

### Avoid premature layering

This repo does not use a heavy domain/application/persistence architecture, and that is intentional. The current structure is module-oriented:

- command modules
- config/models
- service integration helpers
- scaffold/templates

Future refactors should preserve clarity, but should not introduce extra layers unless they simplify a real maintenance problem.

## Planned Evolution

The repo now has explicit bootstrap slices for the first Debian-family host target: assessment, Cloudflare tunnel provisioning, host runtime convergence, shared-group `cloudflared` wiring, and final readiness validation. This is still an operator-run sequence, not a single unattended first-run wizard.

Future bootstrap work should continue building on the existing bootstrap layer as an orchestrator. It should call into the existing Cloudflare and `cloudflared` helpers where possible rather than scattering host-provisioning logic across unrelated command modules.

If the planned mail-provider milestone lands, the same rule should apply:

- a future [`homesrvctl/commands/mail_cmd.py`](homesrvctl/commands/mail_cmd.py) should define the operator-facing mail verbs
- a future provider module such as [`homesrvctl/mail_providers/ses.py`](homesrvctl/mail_providers/ses.py) should own AWS SDK/API interactions, identity inspection, and SES-specific status normalization
- the TUI should consume mail-provider behavior through the JSON command surface rather than reaching into provider helpers directly
- app templates should remain separate from the mail admin surface; per-app mail runtime wiring is not the same concern as domain/admin inspection

## Testing Model

Current verification centers on:
- command behavior
- JSON output stability
- config resolution
- Cloudflare and `cloudflared` integration helpers
- scaffold generation

Primary local verification commands are recorded in [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md).

## Evolution Rules

- Prefer small, end-to-end slices.
- Prefer idempotent mutation behavior.
- Add regression tests when:
  - a command gains a new runtime branch
  - a command gains a new output mode
  - a public contract changes
- Update this document when the repo structure or module responsibilities change materially.
