# Roadmap

`homesrvctl` is intentionally small and operationally focused. This roadmap is a lightweight backlog for the next useful upgrades.

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
- Consider broadening the `cloudflared` command surface beyond status/restart if more service controls are needed.
- Consider `cloudflared reload` if a safe reload mechanism exists for the detected runtime.

## Recently Completed

- Added `homesrvctl domain add` support for Cloudflare DNS upserts plus `cloudflared` ingress reconciliation.
- Added optional `--restart-cloudflared` support for domain-changing commands.
- Added `homesrvctl domain remove` for DNS and ingress teardown.
- Added `homesrvctl domain status` with `ok`, `partial`, and `misconfigured` reporting.
- Added a repairability signal and suggested repair command to `homesrvctl domain status`.
- Added domain-status diagnostics for earlier ingress rules that shadow the requested hostname.
- Added domain-status diagnostics for ambiguous Cloudflare DNS state such as multiple records for the same hostname.
- Added explicit apex-only versus wildcard-only coverage diagnostics for domain status.
- Added `homesrvctl domain repair` to converge stale or partial domain state.
- Added `--json` output for `domain add`, `domain repair`, and `domain remove`.
- Added a shared `cloudflared` service-management abstraction for runtime detection and restart handling.
- Added `--json` output for `domain status`, `validate`, and `doctor`.
- Added `--json` output for `list`.
- Added `cloudflared status` and `cloudflared restart` commands.
- Added `cloudflared config-test` with `cloudflared`-CLI validation plus structural fallback.
- Added `cloudflared logs` guidance for systemd and Docker runtimes.
- Added `--json` output for `cloudflared restart`.
- Added `--json` output for `up`, `down`, and `restart`.
- Added `--json` output for `site init` and `app init`.
- Added scaffold JSON metadata for template names and rendered template mappings.
- Added a shared top-level `schema_version` to all JSON command output.
- Added `config init --json` with created-versus-overwritten reporting.
- Added a real multi-file `node` app scaffold under `homesrvctl/templates/app/node/`.
- Added a real multi-file `python` app scaffold under `homesrvctl/templates/app/python/`.
- Moved the placeholder app scaffold under `homesrvctl/templates/app/placeholder/`.
- Added stack-local `homesrvctl.yml` overrides for `docker_network` and `traefik_url`.
- Taught scaffold commands to write stack-local routing overrides and taught domain/doctor flows to honor apex stack `traefik_url` overrides.
- Added packaging and release automation for tagged versions.
- Added a GitHub Actions release workflow for `vX.Y.Z` tags that builds artifacts and publishes GitHub Releases.
- Added a TestPyPI-first trusted publishing step to the tagged release workflow before GitHub Release creation.
- Added a production PyPI trusted publishing step after successful TestPyPI publication.
- Reused the shared Python checks workflow as the release gate before artifact publishing.
- Chose `project.version` in `pyproject.toml` plus matching `vX.Y.Z` tags as the release version source of truth.
- Chose GitHub releases as the public release channel and enabled both TestPyPI and PyPI trusted publishing in the tagged release flow.
- Added written release instructions and GitHub-generated release notes discipline.
- Added CI via GitHub Actions and updated it to Node 24-compatible action versions.
- Cleaned the public repository for release with generic examples, neutral defaults, and MIT licensing metadata.

## Later

- Expand `app init` templates beyond the current placeholder and minimal scaffolds.
- Consider additional templates for common self-hosted app patterns such as a static app plus API.
- Decide how much opinionated app bootstrap belongs in `homesrvctl` versus remaining a minimal Compose scaffold generator.
- Publish to PyPI in addition to GitHub Releases.
- Choose the PyPI publishing trust model.
  Decide between PyPI trusted publishing and API-token publishing, with trusted publishing preferred if the repository and package setup fit.
- Create and document the PyPI project.
  Reserve the package name, populate package metadata needed for PyPI, and verify the long description renders correctly before enabling publication.
- Extend the release workflow for PyPI publication.
  Keep GitHub Releases as the current artifact channel, add a publish-on-tag step after artifact build and release gating, and ensure failures are isolated clearly between GitHub Release creation and PyPI upload.
- Add a safe release path for initial PyPI rollout.
  Start with TestPyPI or a manual dry-run path, confirm the built wheel and sdist install cleanly, then enable production PyPI publishing.
- Update public install guidance once PyPI is live.
  Change the README to prefer `pip install homesrvctl`, keep the GitHub install path as a fallback, and update `RELEASING.md` with the exact PyPI release flow.
- Add richer configuration options for more than one local ingress target or routing profile.
- Support more than one local ingress URL when operators do not front everything through the same Traefik listener.
- Add product-level support for per-domain or per-stack ingress overrides.
  Allow one hosted stack to target a non-default local ingress URL without forcing a second global config file.
- Add product-level support for per-domain or per-stack Docker network overrides.
  Make it possible for stacks to join a non-default external network when the operator does not use the standard shared network.
- Define the routing-profile model before adding more flags.
  Decide whether multi-profile hosting belongs in one config file, named profiles, or separate config environments so the UX stays coherent.
- Decide how domain lifecycle commands should honor routing overrides.
  Ensure `domain add`, `status`, `repair`, and `remove` can report and reconcile the correct ingress target when a domain is not using the default profile.
- Add product-focused tests for non-default routing setups.
  Cover alternate ingress URLs, alternate Docker networks, and mixed default-versus-overridden stacks so the operator model stays reliable.
- Consider broader Cloudflare API coverage where it meaningfully improves reliability over CLI-based flows.
- Review whether tunnel inspection or management should move further from `cloudflared` CLI usage to the API.
- Evaluate whether any remaining CLI-only flows are fragile enough to justify API replacements.
- Keep the current hybrid model unless an API migration clearly reduces operator risk.
