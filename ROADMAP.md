# Roadmap

`homectl` is intentionally small and operationally focused. This roadmap is a lightweight backlog for the next useful upgrades.

## Now

- Tighten validation and error messages around partial or conflicting domain state.
- Make ambiguous state messages more explicit about what `repair` can fix automatically versus what requires manual cleanup.
- Review remaining non-JSON error paths and make sure they stay concise and actionable.
- Keep the test suite and CI green as the CLI surface grows.
- Keep local verification aligned with GitHub Actions so CI failures are reproducible locally.
- Add regression tests whenever a command grows a new output mode or runtime branch.
- Watch for output-shape drift in the JSON commands as more fields get added.
- Preserve a simple operator model: one command should do the obvious thing, with `--dry-run` available for preview.
- Avoid adding command flags that overlap confusingly unless they clearly unlock automation or safety.
- Keep command naming consistent across lifecycle flows: add, status, repair, remove.
- Prefer convergent/idempotent behavior for mutation commands so reruns stay safe.

## Next

- Add more domain-level diagnostics and repair hints for unsafe or ambiguous `cloudflared` config states.
- Detect and explain wildcard-only routing cases where the apex is still missing.
- Detect and explain DNS records of the wrong type or target with clearer remediation text.
- Consider surfacing “repairable” versus “manual-fix required” in status output.
- Add machine-readable output to additional commands where scripting would help beyond the current status/reporting set.
- Review whether `config init` should support `--json` or another machine-readable mode.
- Decide whether the scaffold commands should report rendered template names in JSON, not just file paths.
- Decide whether `cloudflared status` and restart output should expose a stable schema version for automation.
- Consider broadening the `cloudflared` command surface beyond status/restart if more service controls are needed.
- Consider `cloudflared reload` if a safe reload mechanism exists for the detected runtime.
- Consider `cloudflared config test` or an equivalent validation command layered on the current YAML checks.

## Recently Completed

- Added `homectl domain add` support for Cloudflare DNS upserts plus `cloudflared` ingress reconciliation.
- Added optional `--restart-cloudflared` support for domain-changing commands.
- Added `homectl domain remove` for DNS and ingress teardown.
- Added `homectl domain status` with `ok`, `partial`, and `misconfigured` reporting.
- Added a repairability signal and suggested repair command to `homectl domain status`.
- Added domain-status diagnostics for earlier ingress rules that shadow the requested hostname.
- Added domain-status diagnostics for ambiguous Cloudflare DNS state such as multiple records for the same hostname.
- Added explicit apex-only versus wildcard-only coverage diagnostics for domain status.
- Added `homectl domain repair` to converge stale or partial domain state.
- Added `--json` output for `domain add`, `domain repair`, and `domain remove`.
- Added a shared `cloudflared` service-management abstraction for runtime detection and restart handling.
- Added `--json` output for `domain status`, `validate`, and `doctor`.
- Added `--json` output for `list`.
- Added `cloudflared status` and `cloudflared restart` commands.
- Added `cloudflared logs` guidance for systemd and Docker runtimes.
- Added `--json` output for `cloudflared restart`.
- Added `--json` output for `up`, `down`, and `restart`.
- Added `--json` output for `site init` and `app init`.
- Added CI via GitHub Actions and updated it to Node 24-compatible action versions.
- Cleaned the public repository for release with generic examples, neutral defaults, and MIT licensing metadata.

## Later

- Expand `app init` templates beyond the current placeholder and minimal scaffolds.
- Add a more complete Node app scaffold beyond the current README placeholder.
- Consider additional templates for common self-hosted app patterns such as a static app plus API, or a simple Python service.
- Decide how much opinionated app bootstrap belongs in `homectl` versus remaining a minimal Compose scaffold generator.
- Add packaging and release automation for tagged versions.
- Add a GitHub Actions release workflow for tags.
- Decide whether to publish to PyPI or stay GitHub-install only.
- Add versioning/release notes discipline once a public release cadence exists.
- Add richer configuration options for more than one local ingress target or routing profile.
- Support more than one local ingress URL when operators do not front everything through the same Traefik listener.
- Consider per-domain or per-stack overrides for ingress target and docker network.
- Decide whether multi-profile hosting belongs in one config file or separate config environments.
- Consider broader Cloudflare API coverage where it meaningfully improves reliability over CLI-based flows.
- Review whether tunnel inspection or management should move further from `cloudflared` CLI usage to the API.
- Evaluate whether any remaining CLI-only flows are fragile enough to justify API replacements.
- Keep the current hybrid model unless an API migration clearly reduces operator risk.
