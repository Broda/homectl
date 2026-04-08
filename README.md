# homesrvctl

MIT licensed.

`homesrvctl` is a production-oriented Python CLI for managing a home-server hosting platform built around:

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

`homesrvctl` intentionally preserves the existing operating model:

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
pip install "homesrvctl @ https://github.com/Broda/homesrvctl/archive/refs/tags/v0.2.0.tar.gz"
```

The published Python distribution name is `homesrvctl`. The CLI command remains `homesrvctl`.

`homesrvctl` currently uses GitHub releases as its public release channel. Tagged releases publish to TestPyPI first. Production PyPI publishing is not enabled yet.

## Configuration

Initialize the default config:

```bash
homesrvctl config init
homesrvctl config init --json
```

That writes:

```text
~/.config/homesrvctl/config.yml
```

Default config shape:

```yaml
tunnel_name: homesrvctl-tunnel
sites_root: /srv/homesrvctl/sites
docker_network: web
traefik_url: http://localhost:8081
cloudflared_config: /etc/cloudflared/config.yml
cloudflare_api_token: ""
```

`cloudflare_api_token` may also be supplied via the `CLOUDFLARE_API_TOKEN` environment variable.
It should have at least `Zone:Read` and `DNS:Edit` for the zones you want `homesrvctl domain add` to manage.

## Usage

Create config:

```bash
homesrvctl config init
```

Add DNS tunnel routes for a domain:

```bash
homesrvctl domain add example.com
homesrvctl domain status example.com
homesrvctl domain repair example.com --dry-run
homesrvctl domain remove example.com --dry-run
```

Scaffold and run a static site:

```bash
homesrvctl site init example.com
homesrvctl up example.com
```

Scaffold and run a subdomain site:

```bash
homesrvctl site init notes.example.com
homesrvctl up notes.example.com
```

Scaffold a Node app:

```bash
homesrvctl app init app.example.com --template node
```

Scaffold a Python app:

```bash
homesrvctl app init api.example.com --template python
```

Inspect the stack:

```bash
homesrvctl list
homesrvctl cloudflared status
homesrvctl cloudflared config-test
homesrvctl cloudflared logs
homesrvctl validate
homesrvctl doctor test.example.com
```

Preview without changing anything:

```bash
homesrvctl domain add example.com --dry-run
homesrvctl domain add example.com --dry-run --restart-cloudflared
homesrvctl domain add example.com --dry-run --json
homesrvctl domain status example.com
homesrvctl domain status example.com --json
homesrvctl domain repair example.com --dry-run --json
homesrvctl domain remove example.com --dry-run --json
homesrvctl list --json
homesrvctl cloudflared status --json
homesrvctl cloudflared config-test --json
homesrvctl cloudflared logs --follow --json
homesrvctl cloudflared restart --dry-run
homesrvctl cloudflared restart --dry-run --json
homesrvctl up example.com --dry-run --json
homesrvctl down example.com --dry-run --json
homesrvctl restart example.com --dry-run --json
homesrvctl validate --json
homesrvctl doctor example.com --json
homesrvctl site init example.com --dry-run --json
homesrvctl app init app.example.com --template node --dry-run --json
homesrvctl app init api.example.com --template python --dry-run --json
homesrvctl up example.com --dry-run
```

## Command Overview

- `homesrvctl config init [--path PATH] [--force] [--json]`
- `homesrvctl domain add <domain> [--dry-run] [--json] [--restart-cloudflared]`
- `homesrvctl domain status <domain> [--json]`
- `homesrvctl domain repair <domain> [--dry-run] [--json] [--restart-cloudflared]`
- `homesrvctl domain remove <domain> [--dry-run] [--json] [--restart-cloudflared]`
- `homesrvctl site init <hostname> [--force] [--dry-run] [--json]`
- `homesrvctl app init <hostname> [--template static|placeholder|node|python] [--force] [--dry-run] [--json]`
- `homesrvctl up <hostname> [--dry-run] [--json]`
- `homesrvctl down <hostname> [--dry-run] [--json]`
- `homesrvctl restart <hostname> [--dry-run] [--json]`
- `homesrvctl list [--json]`
- `homesrvctl cloudflared status [--json]`
- `homesrvctl cloudflared config-test [--json]`
- `homesrvctl cloudflared logs [--follow] [--json]`
- `homesrvctl cloudflared restart [--dry-run] [--json]`
- `homesrvctl validate [--json]`
- `homesrvctl doctor <hostname> [--json]`

## Notes

- `domain add` uses the Cloudflare DNS API to manage apex and wildcard records for the requested zone.
- `domain add`, `domain repair`, and `domain remove` support `--json` for machine-readable mutation results.
- all `--json` commands include a top-level `schema_version` so automation can pin to a known output shape.
- `config init --json` reports whether the config file was created or overwritten.
- `domain status` reports expected tunnel target, apex and wildcard DNS state, apex and wildcard `cloudflared` ingress state, whether a route is being shadowed by an earlier ingress rule, whether Cloudflare DNS is ambiguous or of the wrong type, whether coverage is apex-only or wildcard-only, and whether `homesrvctl domain repair` is likely to fix the current state automatically.
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
