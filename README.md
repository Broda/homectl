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

## Configuration

Initialize the default config:

```bash
homectl config init
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

Scaffold an app placeholder:

```bash
homectl app init app.example.com --template placeholder
```

Inspect the stack:

```bash
homectl list
homectl validate
homectl doctor test.example.com
```

Preview without changing anything:

```bash
homectl domain add example.com --dry-run
homectl site init example.com --dry-run
homectl up example.com --dry-run
```

## Command Overview

- `homectl config init`
- `homectl domain add <domain> [--dry-run]`
- `homectl site init <hostname> [--force] [--dry-run]`
- `homectl app init <hostname> [--template static|placeholder|node] [--force] [--dry-run]`
- `homectl up <hostname> [--dry-run]`
- `homectl down <hostname> [--dry-run]`
- `homectl restart <hostname> [--dry-run]`
- `homectl list`
- `homectl validate`
- `homectl doctor <hostname>`

## Notes

- `domain add` uses the Cloudflare DNS API to manage apex and wildcard records for the requested zone.
- `domain add` resolves the tunnel target from the local `cloudflared` tunnel configuration and does not depend on the active `cloudflared tunnel login` zone.
- `site init` and `app init` generate Traefik-safe router and service identifiers from the hostname.
- All generated Compose files join the external Docker network configured in `docker_network`.
- In v1, `app init` uses templates designed to be expanded later. The `node` template is a placeholder scaffold rather than a full Node application bootstrap.
