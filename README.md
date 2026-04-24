# Home Server Controller (`homesrvctl`)

MIT licensed.

`homesrvctl` is a production-oriented Python CLI for operating a home-server hosting platform built around:

- Cloudflare DNS and Cloudflare Tunnel
- `cloudflared`
- Traefik
- Docker Compose
- a shared external Docker network, typically `web`

It helps with the repeatable operator work around self-hosted sites:

- bootstrap a first Debian-family Raspberry Pi host
- create or inspect the shared Cloudflare Tunnel setup
- add and repair apex plus wildcard domain routes
- reconcile local `cloudflared` ingress entries
- scaffold static sites and app stacks
- start, stop, validate, and diagnose per-hostname Compose stacks
- inspect the platform through a Textual terminal dashboard

## Operating Model

`homesrvctl` intentionally keeps the hosting model simple:

- Cloudflare Tunnel handles domain-level ingress.
- Traefik handles local hostname routing.
- Docker Compose runs each site or app.
- Once `example.com` and `*.example.com` point at the tunnel, additional subdomains usually only need local server changes.

For an already-built platform, `homesrvctl` manages domains, scaffolds, validation, and local operations. For the first supported fresh-host path, the shipped bootstrap commands can converge Docker, Compose, Traefik, `cloudflared`, shared directories, service wiring, a Cloudflare tunnel, and the main config as explicit operator-run slices.

`homesrvctl` is not a full infrastructure-as-code framework, a generic app generator, a Docker/Traefik replacement, or a broad Cloudflare administration console.

## Installation

From PyPI:

```bash
pipx install homesrvctl
```

Upgrade an existing PyPI install:

```bash
pipx upgrade homesrvctl
```

If `pipx` reports that `~/.local/bin/homesrvctl` already exists and is not the expected pipx symlink, inspect the active command path:

```bash
homesrvctl version --json
homesrvctl install status
```

From a tagged GitHub release:

```bash
pip install "homesrvctl @ https://github.com/Broda/homesrvctl/archive/refs/tags/vX.Y.Z.tar.gz"
```

For local development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

The published Python distribution name is `homesrvctl`. The CLI command is also `homesrvctl`.

## Documentation

Detailed operator guides live in the project wiki:

- Wiki home: `https://github.com/Broda/homesrvctl/wiki`
- Getting started: `https://github.com/Broda/homesrvctl/wiki/Getting-Started`
- Bootstrap plan: `https://github.com/Broda/homesrvctl/wiki/Bootstrap-Plan`
- Configuration: `https://github.com/Broda/homesrvctl/wiki/Configuration`
- Domain workflow: `https://github.com/Broda/homesrvctl/wiki/Domain-Workflow`
- Tunnel inspection: `https://github.com/Broda/homesrvctl/wiki/Tunnel-Inspection`
- Terminal dashboard: `https://github.com/Broda/homesrvctl/wiki/Terminal-Dashboard`
- Release process: `https://github.com/Broda/homesrvctl/wiki/Release-Process`

Repo-maintenance docs:

- [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) records scope, assumptions, and verification commands.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) records module boundaries and public contracts.
- [`ROADMAP.md`](ROADMAP.md) records current and proposed work.
- [`CHANGELOG.md`](CHANGELOG.md) records user-facing changes.
- [`RELEASING.md`](RELEASING.md) records the tagged release process.

## Quick Start

Create and inspect the config:

```bash
homesrvctl config init
homesrvctl config show
```

Bootstrap a first supported Debian-family host:

```bash
homesrvctl bootstrap assess
sudo homesrvctl bootstrap runtime
homesrvctl bootstrap tunnel --account-id <cloudflare-account-id>
sudo homesrvctl bootstrap wiring
homesrvctl bootstrap validate
```

Scaffold and run a static site:

```bash
homesrvctl domain add example.com --restart-cloudflared
homesrvctl site init example.com
homesrvctl up example.com
homesrvctl doctor example.com
```

Scaffold an app stack:

```bash
homesrvctl app detect ./existing-app
homesrvctl app init app.example.com --template node
homesrvctl up app.example.com
homesrvctl doctor app.example.com
```

Stop and delete a local stack directory:

```bash
homesrvctl cleanup test.example.com --dry-run
homesrvctl cleanup test.example.com --force
```

Launch the terminal dashboard:

```bash
homesrvctl
```

The explicit dashboard command is also available:

```bash
homesrvctl tui
```

## Configuration Summary

The default config path is:

```text
~/.config/homesrvctl/config.yml
```

Default config shape:

```yaml
tunnel_name: homesrvctl-tunnel
sites_root: /srv/homesrvctl/sites
docker_network: web
traefik_url: http://localhost:80
cloudflared_config: /srv/homesrvctl/cloudflared/config.yml
cloudflare_api_token: ""
profiles: {}
```

The first-class shared `cloudflared` setup model uses:

- config: `/srv/homesrvctl/cloudflared/config.yml`
- tunnel credentials JSON: `/srv/homesrvctl/cloudflared/<tunnel-id>.json`
- ownership: `root:homesrvctl`
- permissions:
  - directory `750`
  - files `640`

The tunnel credentials JSON is secret material. Use the dedicated `homesrvctl` group for trusted operator access rather than making credentials world-readable.

The intended permission model is one-time privileged bootstrap followed by non-root operation. `bootstrap runtime` creates the shared group and group-writable stack/config directories, and `bootstrap wiring` installs systemd wiring plus a narrow sudoers rule that lets `homesrvctl` group members restart or reload only the `cloudflared` service. Log out and back in after group membership changes so the current shell picks up `homesrvctl` and `docker` access.

For the shipped bootstrap Traefik runtime, `traefik_url` should target the public web entrypoint on host port 80. Host port 8081 is reserved for the Traefik dashboard/API and should not be used as the Cloudflare Tunnel ingress target.

`cloudflare_api_token` may also be supplied through `CLOUDFLARE_API_TOKEN`. Domain management needs `Zone:Read` and `DNS:Edit`. Tunnel inspection and bootstrap tunnel provisioning need the relevant Cloudflare Tunnel account permissions.

Routing precedence is:

1. Global defaults from top-level `docker_network` and `traefik_url`.
2. Named profile values from `profiles`.
3. Direct stack-local overrides from `/srv/homesrvctl/sites/<hostname>/homesrvctl.yml`.

Supported stack-local keys:

```yaml
profile: edge
docker_network: edge
traefik_url: http://localhost:9000
```

## Common Workflows

Inspect host and tunnel state:

```bash
homesrvctl validate
homesrvctl tunnel status
homesrvctl cloudflared status
homesrvctl cloudflared setup
homesrvctl cloudflared config-test
homesrvctl cloudflared logs
```

Manage a domain:

```bash
homesrvctl domain add example.com --restart-cloudflared
homesrvctl domain status example.com
homesrvctl domain repair example.com --dry-run
homesrvctl domain repair example.com --restart-cloudflared
homesrvctl domain remove example.com --dry-run
```

Scaffold common stack types:

```bash
homesrvctl app detect ./existing-app
homesrvctl site init example.com
homesrvctl app init app.example.com --template static
homesrvctl app init portal.example.com --template static-api
homesrvctl app init api.example.com --template python
homesrvctl app init web.example.com --template node
homesrvctl app init blog.example.com --template jekyll
homesrvctl app init product.example.com --template rust-react-postgres
```

Use routing overrides:

```bash
homesrvctl site init example.com --profile edge
homesrvctl app init app.example.com --template node --docker-network edge
homesrvctl app init api.example.com --template python --traefik-url http://localhost:9000
```

Override template ports where supported:

```bash
homesrvctl app init app.example.com --template node --port app=3100
homesrvctl app init portal.example.com --template static-api --port api=8100
homesrvctl ports list --stack portal.example.com
```

Preview mutations and consume JSON:

```bash
homesrvctl domain add example.com --dry-run --json
homesrvctl app init app.example.com --template node --dry-run --json
homesrvctl up app.example.com --dry-run --json
homesrvctl validate --json
```

All JSON commands include a top-level `schema_version`.

## Command Overview

- `homesrvctl config init [--path PATH] [--force] [--json]`
- `homesrvctl config show [--path PATH] [--stack HOSTNAME] [--json]`
- `homesrvctl bootstrap assess [--path PATH] [--json]`
- `homesrvctl bootstrap runtime [--path PATH] [--operator-user USER] [--force] [--dry-run] [--json]`
- `homesrvctl bootstrap tunnel [--path PATH] [--account-id ACCOUNT_ID] [--name NAME] [--force] [--json]`
- `homesrvctl bootstrap wiring [--path PATH] [--force] [--dry-run] [--json]`
- `homesrvctl bootstrap validate [--path PATH] [--json]`
- `homesrvctl tunnel status [--json]`
- `homesrvctl domain add <domain> [--dry-run] [--json] [--restart-cloudflared]`
- `homesrvctl domain status <domain> [--json]`
- `homesrvctl domain repair <domain> [--dry-run] [--json] [--restart-cloudflared]`
- `homesrvctl domain remove <domain> [--dry-run] [--json] [--restart-cloudflared]`
- `homesrvctl site init <hostname> [--force] [--dry-run] [--json] [--profile NAME] [--docker-network NETWORK] [--traefik-url URL]`
- `homesrvctl app detect <source_path> [--json]`
- `homesrvctl app init <hostname> [--template static|static-api|placeholder|node|python|jekyll|rust-react-postgres] [--port NAME=PORT]... [--force] [--dry-run] [--json] [--profile NAME] [--docker-network NETWORK] [--traefik-url URL]`
- `homesrvctl ports list [--stack HOSTNAME] [--json]`
- `homesrvctl up <hostname> [--dry-run] [--json]`
- `homesrvctl down <hostname> [--dry-run] [--json]`
- `homesrvctl restart <hostname> [--dry-run] [--json]`
- `homesrvctl list [--json]`
- `homesrvctl tui [--refresh-seconds FLOAT]`
- `homesrvctl cloudflared status [--json]`
- `homesrvctl cloudflared setup [--json]`
- `homesrvctl cloudflared config-test [--json]`
- `homesrvctl cloudflared logs [--follow] [--json]`
- `homesrvctl cloudflared restart [--dry-run] [--json]`
- `homesrvctl cloudflared reload [--dry-run] [--json]`
- `homesrvctl validate [--json]`
- `homesrvctl doctor <hostname> [--json]`

## Notes

- `bootstrap` commands are explicit slices, not a single unattended installer.
- `homesrvctl` does not prompt for `sudo`; privileged setup steps print or require the commands to run.
- After bootstrap, the normal operator should not need root for stack scaffolding, domain ingress changes, Docker Compose stack lifecycle, or `cloudflared` restart/reload through the scoped policy.
- `domain add`, `domain repair`, and `domain remove` preflight local ingress mutation safety before writing DNS.
- `domain status`, `doctor`, `validate`, and `cloudflared config-test` distinguish blocking ingress problems from advisory wildcard-ordering risks.
- `cloudflared reload` is available only when the detected runtime exposes a safe reload command; `restart` remains the predictable cross-runtime baseline.
- `site init` is the narrow static scaffold; `app init --template static` is the richer nginx-backed static app baseline.
- `app detect` is read-only. It reports likely source families and next steps before any wrapper/adoption mutation is attempted.
- The Textual TUI is backed by existing JSON command surfaces. It requires an interactive terminal and the same local runtime access as the CLI commands it launches.
