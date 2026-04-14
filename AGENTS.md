# Development Guide

This file is a lightweight development contract for this repository. It is intentionally much simpler than a full governance framework.

## Before Meaningful Changes

Check:
- [`ROADMAP.md`](ROADMAP.md)
- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`CHANGELOG.md`](CHANGELOG.md)
- [`FILE_MAP.md`](FILE_MAP.md)

The goal is not ceremony. The goal is to avoid making structural or user-visible changes blindly.

## Scope Discipline

Before implementing a non-trivial change:
- identify the milestone or task it belongs to
- keep the slice narrow
- avoid bundling unrelated cleanups into the same change

## Public Contract Discipline

Treat these as public contracts:
- CLI command names and major flags
- JSON output shapes
- config file formats
- stack-local `homesrvctl.yml` format
- documented scaffold output layout

If one of these changes:
- update tests
- update docs
- update `CHANGELOG.md`

## Documentation Update Rules

Update the relevant docs when they are affected:
- [`README.md`](README.md) for public usage changes
- [`CHANGELOG.md`](CHANGELOG.md) for user-visible changes
- [`ROADMAP.md`](ROADMAP.md) when milestone scope changes
- [`ARCHITECTURE.md`](ARCHITECTURE.md) when structure or ownership changes
- [`FILE_MAP.md`](FILE_MAP.md) when repo layout changes materially
- [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) when core development assumptions change

For code changes that affect public behavior, operator workflows, configuration, scaffolding, commands, or releases:
- update the relevant repo docs in the same slice
- update the GitHub wiki in the same slice when the change affects user-facing guidance
- prefer committing code and the matching docs/wiki updates together rather than treating docs as a later cleanup
- when a sibling wiki checkout exists at `../homesrvctl.wiki`, run `scripts/check_wiki_sync.sh` before closing the slice

## Verification Expectations

Run the standard local verification commands when they are relevant:

```bash
python3 -m compileall homesrvctl tests
.venv/bin/python -m pytest -q
.venv/bin/python -m build
```

At minimum:
- run compile plus tests for code changes
- run the build step when packaging, release, or metadata changes are involved
- run `scripts/check_wiki_sync.sh` when user-facing behavior, scaffolds, commands, or docs changed and a sibling wiki checkout is present

## Architectural Boundaries

- Command modules should orchestrate rather than reimplement lower-level helpers.
- Cloudflare API behavior belongs in `homesrvctl/cloudflare.py`.
- `cloudflared` config/runtime behavior belongs in `homesrvctl/cloudflared.py` and `homesrvctl/cloudflared_service.py`.
- Config shape and resolution belong in `homesrvctl/config.py` and `homesrvctl/models.py`.
- Template families should stay organized under `homesrvctl/templates/`.

## Working Style

- Prefer convergent, idempotent behavior for mutation commands.
- Prefer explicit output over clever output.
- Prefer a small number of clear flags over overlapping modes.
- Prefer adding regression tests when a command gains:
  - a new runtime branch
  - a new output mode
  - a new public contract surface

## Rule Of Thumb

Keep the project structured enough to avoid drift, but lightweight enough that the structure does not become the project.
