# homectl

MIT licensed.

`homectl` is a production-oriented Python CLI for managing a home-server hosting platform built around:

- Cloudflare DNS
- a locally managed Cloudflare Tunnel via `cloudflared`
- Traefik for local hostname routing
- Docker Compose for workloads
- a shared external Docker network named `web`

It automates the repetitive parts of:

- adding apex and wildcard tunnel DNS routes for a new domain
- reconciling local `cloudflared` ingress entries for new domains
- scaffolding static sites and app directories
- starting and stopping per-hostname Compose stacks
- validating the local hosting environment
- diagnosing a specific hostname

## Assumptions

`homectl` intentionally preserves the existing operating model:

- Cloudflare Tunnel handles domain-level ingress
- Traefik handles hostname routing on the server
- Docker Compose runs each site or app
- once `example.com` and `*.example.com` are routed to the tunnel, additional subdomains only need local server changes

The tool assumes:

- Linux on the server
- `cloudflared` is already installed and configured
- `docker` and `docker compose` are already installed
- Traefik is already working
- a shared external Docker network such as `web` already exists
- the Cloudflare Tunnel is locally managed and already functional

## Installation

From the project directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

From a tagged GitHub release:

```bash
pip install "homectl @ https://github.com/Broda/homectl/archive/refs/tags/v0.1.0.tar.gz"
```

`homectl` currently uses GitHub releases as its public release channel. PyPI publishing is not enabled yet.

## Configuration

Initialize the default config:

```bash
homectl config init
homectl config init --json
```

That writes:

```text
~/.config/homectl/config.yml
```

Default config shape:

```yaml
tunnel_name: homectl-tunnel
sites_root: /srv/homectl/sites
docker_network: web
traefik_url: http://localhost:8081
cloudflared_config: /etc/cloudflared/config.yml
cloudflare_api_token: ""
```

`cloudflare_api_token` may also be supplied via the `CLOUDFLARE_API_TOKEN` environment variable.
It should have at least `Zone:Read` and `DNS:Edit` for the zones you want `homectl domain add` to manage.

## Usage

Create config:

```bash
homectl config init
```

Add DNS tunnel routes for a domain:

```bash
homectl domain add example.com
homectl domain status example.com
homectl domain repair example.com --dry-run
homectl domain remove example.com --dry-run
```

Scaffold and run a static site:

```bash
homectl site init example.com
homectl up example.com
```

Scaffold and run a subdomain site:

```bash
homectl site init notes.example.com
homectl up notes.example.com
```

Scaffold a Node app:

```bash
homectl app init app.example.com --template node
```

Scaffold a Python app:

```bash
homectl app init api.example.com --template python
```

Inspect the stack:

```bash
homectl list
homectl cloudflared status
homectl cloudflared config-test
homectl cloudflared logs
homectl validate
homectl doctor test.example.com
```

Preview without changing anything:

```bash
homectl domain add example.com --dry-run
homectl domain add example.com --dry-run --restart-cloudflared
homectl domain add example.com --dry-run --json
homectl domain status example.com
homectl domain status example.com --json
homectl domain repair example.com --dry-run --json
homectl domain remove example.com --dry-run --json
homectl list --json
homectl cloudflared status --json
homectl cloudflared config-test --json
homectl cloudflared logs --follow --json
homectl cloudflared restart --dry-run
homectl cloudflared restart --dry-run --json
homectl up example.com --dry-run --json
homectl down example.com --dry-run --json
homectl restart example.com --dry-run --json
homectl validate --json
homectl doctor example.com --json
homectl site init example.com --dry-run --json
homectl app init app.example.com --template node --dry-run --json
homectl app init api.example.com --template python --dry-run --json
homectl up example.com --dry-run
```

## Command Overview

- `homectl config init [--path PATH] [--force] [--json]`
- `homectl domain add <domain> [--dry-run] [--json] [--restart-cloudflared]`
- `homectl domain status <domain> [--json]`
- `homectl domain repair <domain> [--dry-run] [--json] [--restart-cloudflared]`
- `homectl domain remove <domain> [--dry-run] [--json] [--restart-cloudflared]`
- `homectl site init <hostname> [--force] [--dry-run] [--json]`
- `homectl app init <hostname> [--template static|placeholder|node|python] [--force] [--dry-run] [--json]`
- `homectl up <hostname> [--dry-run] [--json]`
- `homectl down <hostname> [--dry-run] [--json]`
- `homectl restart <hostname> [--dry-run] [--json]`
- `homectl list [--json]`
- `homectl cloudflared status [--json]`
- `homectl cloudflared config-test [--json]`
- `homectl cloudflared logs [--follow] [--json]`
- `homectl cloudflared restart [--dry-run] [--json]`
- `homectl validate [--json]`
- `homectl doctor <hostname> [--json]`

## Notes

- `domain add` uses the Cloudflare DNS API to manage apex and wildcard records for the requested zone.
- `domain add`, `domain repair`, and `domain remove` support `--json` for machine-readable mutation results.
- all `--json` commands include a top-level `schema_version` so automation can pin to a known output shape.
- `config init --json` reports whether the config file was created or overwritten.
- `domain status` reports expected tunnel target, apex and wildcard DNS state, apex and wildcard `cloudflared` ingress state, whether a route is being shadowed by an earlier ingress rule, whether Cloudflare DNS is ambiguous or of the wrong type, whether coverage is apex-only or wildcard-only, and whether `homectl domain repair` is likely to fix the current state automatically.
- `list`, `domain status`, `validate`, and `doctor` support `--json` for machine-readable output.
- `up`, `down`, and `restart` support `--json` for machine-readable command results.
- `site init` and `app init` support `--json` for machine-readable scaffold results, including the selected template and rendered template-to-output mapping.
- `cloudflared status` reports the detected runtime mode, whether it is active, and the restart command when one is available.
- `cloudflared config-test` prefers `cloudflared tunnel ingress validate --config ...` when the binary is available and falls back to structural YAML/ingress validation otherwise.
- `cloudflared logs` prints the right `journalctl` or `docker logs` command for the detected runtime and supports `--follow` plus `--json`.
- `cloudflared restart` also supports `--json` for automation-friendly dry-run and failure reporting.
- `domain add` also reconciles apex and wildcard hostname entries in the configured `cloudflared` ingress file so new domains route locally to Traefik.
- `domain repair` converges apex and wildcard DNS records and matching `cloudflared` ingress entries to the expected state.
- `domain add` resolves the tunnel target from the local `cloudflared` tunnel configuration and does not depend on the active `cloudflared tunnel login` zone.
- `domain remove` removes apex and wildcard DNS records and matching `cloudflared` ingress entries for the requested zone.
- pass `--restart-cloudflared` to have domain-changing commands restart `cloudflared` automatically when a supported runtime is detected
- without that flag, restart `cloudflared` manually after ingress changes
- `site init` and `app init` generate Traefik-safe router and service identifiers from the hostname.
- All generated Compose files join the external Docker network configured in `docker_network`.
- The `node` app template now generates a runnable multi-file scaffold with `docker-compose.yml`, `Dockerfile`, `package.json`, `.env.example`, and `src/server.js`.
- The `python` app template now generates a runnable multi-file scaffold with `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `.env.example`, and `app/main.py`.
