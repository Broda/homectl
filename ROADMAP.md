# Roadmap

`homectl` is intentionally small and operationally focused. This roadmap is a lightweight backlog for the next useful upgrades.

## Now

- Stabilize the domain lifecycle commands around Cloudflare DNS, `cloudflared`, Traefik, and Docker Compose.
- Keep the test suite and CI green as the CLI surface grows.
- Preserve a simple operator model: one command should do the obvious thing, with `--dry-run` available for preview.

## Next

- Add `homectl domain remove` to tear down apex and wildcard DNS records and matching `cloudflared` ingress entries.
- Add `homectl domain status` or expand `doctor` so domain wiring can be inspected in one place.
- Improve `cloudflared` restart handling beyond the current systemd-focused path.
- Tighten validation and error messages around partial or conflicting domain state.

## Later

- Expand `app init` templates beyond the current placeholder and minimal scaffolds.
- Add packaging and release automation for tagged versions.
- Add richer configuration options for more than one local ingress target or routing profile.
- Consider broader Cloudflare API coverage where it meaningfully improves reliability over CLI-based flows.
