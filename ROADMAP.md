# Roadmap

`homectl` is intentionally small and operationally focused. This roadmap is a lightweight backlog for the next useful upgrades.

## Now

- Harden the `cloudflared` service-management path used after ingress changes.
- Keep the test suite and CI green as the CLI surface grows.
- Preserve a simple operator model: one command should do the obvious thing, with `--dry-run` available for preview.

## Next

- Improve `cloudflared` restart handling beyond the current systemd-focused path.
- Add a `cloudflared` service-management abstraction that can detect and handle systemd, container, and report-only/manual modes.
- Tighten validation and error messages around partial or conflicting domain state.
- Add machine-readable `--json` output for `domain status`, `validate`, and `doctor`.

## Recently Completed

- Added `homectl domain add` support for Cloudflare DNS upserts plus `cloudflared` ingress reconciliation.
- Added optional `--restart-cloudflared` support for domain-changing commands.
- Added `homectl domain remove` for DNS and ingress teardown.
- Added `homectl domain status` with `ok`, `partial`, and `misconfigured` reporting.
- Added `homectl domain repair` to converge stale or partial domain state.
- Added CI via GitHub Actions and updated it to Node 24-compatible action versions.
- Cleaned the public repository for release with generic examples, neutral defaults, and MIT licensing metadata.

## Later

- Expand `app init` templates beyond the current placeholder and minimal scaffolds.
- Add packaging and release automation for tagged versions.
- Add richer configuration options for more than one local ingress target or routing profile.
- Consider broader Cloudflare API coverage where it meaningfully improves reliability over CLI-based flows.
