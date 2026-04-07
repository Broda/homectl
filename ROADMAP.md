# Roadmap

`homectl` is intentionally small and operationally focused. This roadmap is a lightweight backlog for the next useful upgrades.

## Now

- Tighten validation and error messages around partial or conflicting domain state.
- Keep the test suite and CI green as the CLI surface grows.
- Preserve a simple operator model: one command should do the obvious thing, with `--dry-run` available for preview.

## Next

- Add more domain-level diagnostics and repair hints for unsafe or ambiguous `cloudflared` config states.
- Add machine-readable output to additional commands where scripting would help beyond the current status/reporting set.
- Consider broadening the `cloudflared` command surface beyond status/restart if more service controls are needed.

## Recently Completed

- Added `homectl domain add` support for Cloudflare DNS upserts plus `cloudflared` ingress reconciliation.
- Added optional `--restart-cloudflared` support for domain-changing commands.
- Added `homectl domain remove` for DNS and ingress teardown.
- Added `homectl domain status` with `ok`, `partial`, and `misconfigured` reporting.
- Added `homectl domain repair` to converge stale or partial domain state.
- Added a shared `cloudflared` service-management abstraction for runtime detection and restart handling.
- Added `--json` output for `domain status`, `validate`, and `doctor`.
- Added `--json` output for `list`.
- Added `cloudflared status` and `cloudflared restart` commands.
- Added CI via GitHub Actions and updated it to Node 24-compatible action versions.
- Cleaned the public repository for release with generic examples, neutral defaults, and MIT licensing metadata.

## Later

- Expand `app init` templates beyond the current placeholder and minimal scaffolds.
- Add packaging and release automation for tagged versions.
- Add richer configuration options for more than one local ingress target or routing profile.
- Consider broader Cloudflare API coverage where it meaningfully improves reliability over CLI-based flows.
