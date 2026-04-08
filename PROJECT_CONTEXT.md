# Project Context

This document records the working assumptions for `homesrvctl`: what the project is for, what it intentionally does not try to be, and how to verify changes locally.

## Project Purpose

`homesrvctl` is a CLI for operating a home-server hosting setup built around:
- Cloudflare Tunnel
- Traefik
- Docker Compose

The project focuses on:
- scaffolding deployable hostname stacks
- managing domain routing state
- validating local hosting setup
- keeping operator workflows simple and repeatable

## Non-Goals

`homesrvctl` is not trying to be:
- a full infrastructure-as-code framework
- a generic application framework generator
- a replacement for Docker Compose, Traefik, or `cloudflared`
- an all-purpose Cloudflare administration tool

The project should stay narrow enough that operators can understand what each command changes.

## Scaffold Boundary

Scaffolds in `homesrvctl` are meant to produce small, deployable hosting baselines.

They may include:
- Compose
- a minimal Dockerfile
- a minimal runtime entrypoint
- basic static assets
- a small generated README
- healthchecks

They should not include by default:
- large framework starters
- frontend build pipelines
- databases
- auth systems
- migrations
- production app architecture choices

If a new template would require substantial framework-specific machinery, that should be treated as a separate product decision rather than the automatic next scaffold.

## Product Principles

- Correctness over convenience.
- Convergent/idempotent mutation commands over fragile imperative flows.
- Small operator-facing commands over highly abstract orchestration.
- Clear public contracts over accidental output or config drift.
- Local verification should be straightforward and reproducible.

## Public Contracts

Treat these as stable contracts unless there is a clear reason to change them:

- CLI command names and major options
- JSON output shapes
- config file formats
- stack-local override file format
- documented scaffold output layout

If one of these changes, update the relevant docs and tests in the same slice.

## Verification Commands

These are the standard local verification commands for this repository.

### Compile

```bash
python3 -m compileall homesrvctl tests
```

### Test

```bash
.venv/bin/python -m pytest -q
```

### Build

```bash
.venv/bin/python -m build
```

Use the build step when packaging, release automation, or project metadata changes are involved.

## Release Context

- The distribution name is `homesrvctl`.
- The CLI command is `homesrvctl`.
- Tagged releases use `vX.Y.Z`.
- GitHub Releases, TestPyPI, and PyPI are all part of the release path.

Details live in [`RELEASING.md`](RELEASING.md).

## Documentation Expectations

When making meaningful changes:
- update [`CHANGELOG.md`](CHANGELOG.md) for user-visible changes
- update [`ROADMAP.md`](ROADMAP.md) if scope or milestone direction changes
- update [`ARCHITECTURE.md`](ARCHITECTURE.md) if structure or module boundaries change
- update [`FILE_MAP.md`](FILE_MAP.md) if new top-level docs, modules, or template families are added

## Current Development Focus

The roadmap is milestone-based. Before non-trivial work, check the active next milestone in [`ROADMAP.md`](ROADMAP.md) and keep the change aligned with that scope.

## Practical Rule

Do not add process for its own sake. Add structure where it reduces drift, clarifies ownership, or protects public contracts.
