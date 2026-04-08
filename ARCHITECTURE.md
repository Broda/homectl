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
- host the read-only terminal dashboard entrypoint

Should not do:
- embed Cloudflare request details directly
- embed `cloudflared` config parsing logic directly
- spread shell/process logic across individual commands

### Config and model layer

- [`homesrvctl/models.py`](homesrvctl/models.py)
- [`homesrvctl/config.py`](homesrvctl/config.py)

Responsibilities:
- define global config structure
- define stack-local config structure
- resolve config paths and defaults
- load effective stack-local overrides

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
- tunnel-target-related helper logic used by domain flows

This module should stay focused on Cloudflare control-plane behavior, not local runtime orchestration.

### Cloudflared ingress and runtime integration

- [`homesrvctl/cloudflared.py`](homesrvctl/cloudflared.py)
- [`homesrvctl/cloudflared_service.py`](homesrvctl/cloudflared_service.py)

Responsibilities:
- parse and validate `cloudflared` ingress config
- reconcile ingress entries for domain lifecycle commands
- detect `cloudflared` runtime mode
- select restart/log commands appropriate for the detected runtime

Keep a clear separation between:
- config-file semantics
- runtime/process management

### Scaffold and template layer

- [`homesrvctl/templates.py`](homesrvctl/templates.py)
- [`homesrvctl/templates/site`](homesrvctl/templates/site)
- [`homesrvctl/templates/app`](homesrvctl/templates/app)

Responsibilities:
- render scaffold templates
- keep template families organized
- support site and app initialization without making `homesrvctl` a general-purpose framework generator

The per-template directory layout under `templates/app/` is intentional and should be preserved.
Scaffold scope should stay within the philosophy recorded in [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md): small deployable baselines, not framework stacks.

### Shared utilities

- [`homesrvctl/shell.py`](homesrvctl/shell.py)
- [`homesrvctl/utils.py`](homesrvctl/utils.py)

Responsibilities:
- common shell execution behavior
- filesystem helpers
- shared small utilities used by command modules

These helpers should stay generic and reusable rather than accumulating feature-specific logic.

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
- load read-only dashboard data from the existing JSON command surface
- render terminal dashboard views
- manage TUI-local selection and detail state
- keep TUI-specific state and refresh behavior out of the command modules

This layer should stay separate from CLI wiring so future dashboard/view growth does not bloat `homesrvctl/commands`.

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
