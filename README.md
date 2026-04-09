# Home Server Controller (`homesrvctl`)

MIT licensed.

Home Server Controller (`homesrvctl`) is a production-oriented Python CLI for managing a home-server hosting platform built around:

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

From PyPI:

```bash
pip install homesrvctl
```

From a tagged GitHub release:

```bash
pip install "homesrvctl @ https://github.com/Broda/homesrvctl/archive/refs/tags/v0.2.0.tar.gz"
```

The published Python distribution name is `homesrvctl`. The CLI command is also `homesrvctl`.

`homesrvctl` is published to PyPI. GitHub Releases remain available as an additional artifact channel.

## Documentation

- Wiki home: `https://github.com/Broda/homesrvctl/wiki`
- Getting started: `https://github.com/Broda/homesrvctl/wiki/Getting-Started`
- Configuration: `https://github.com/Broda/homesrvctl/wiki/Configuration`
- Domain workflow: `https://github.com/Broda/homesrvctl/wiki/Domain-Workflow`
- Release process: `https://github.com/Broda/homesrvctl/wiki/Release-Process`

## Configuration

Initialize the default config:

```bash
homesrvctl config init
homesrvctl config init --json
homesrvctl config show
homesrvctl config show --stack example.com --json
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

Optional routing profiles may also be defined in the main config:

```yaml
profiles:
  edge:
    docker_network: edge
    traefik_url: http://localhost:9000
  internal:
    docker_network: internal-web
    traefik_url: http://localhost:8082
```

`cloudflare_api_token` may also be supplied via the `CLOUDFLARE_API_TOKEN` environment variable.
It should have at least `Zone:Read` and `DNS:Edit` for the zones you want `homesrvctl domain add` to manage.

Per-stack overrides may also be stored in:

```text
/srv/homesrvctl/sites/<hostname>/homesrvctl.yml
```

Supported stack-local keys:

```yaml
profile: edge
docker_network: edge
traefik_url: http://localhost:9000
```

## Usage

Create config:

```bash
homesrvctl config init
homesrvctl config show
homesrvctl config show --stack example.com --json
homesrvctl site init example.com --profile edge
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

Scaffold a static website:

```bash
homesrvctl app init www.example.com --template static
```

Scaffold a static website plus API:

```bash
homesrvctl app init portal.example.com --template static-api
```

Scaffold a Python app:

```bash
homesrvctl app init api.example.com --template python
```

Scaffold a Jekyll site baseline:

```bash
homesrvctl app init blog.example.com --template jekyll
```

Scaffold a stack with local overrides:

```bash
homesrvctl site init example.com --docker-network edge --traefik-url http://localhost:9000
homesrvctl app init app.example.com --template node --docker-network edge
homesrvctl app init api.example.com --template python --profile edge
```

Inspect the stack:

```bash
homesrvctl list
homesrvctl tui
homesrvctl cloudflared status
homesrvctl cloudflared config-test
homesrvctl cloudflared logs
homesrvctl cloudflared reload --dry-run
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
homesrvctl cloudflared reload --dry-run
homesrvctl cloudflared reload --dry-run --json
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
- `homesrvctl config show [--path PATH] [--stack HOSTNAME] [--json]`
- `homesrvctl domain add <domain> [--dry-run] [--json] [--restart-cloudflared]`
- `homesrvctl domain status <domain> [--json]`
- `homesrvctl domain repair <domain> [--dry-run] [--json] [--restart-cloudflared]`
- `homesrvctl domain remove <domain> [--dry-run] [--json] [--restart-cloudflared]`
- `homesrvctl site init <hostname> [--force] [--dry-run] [--json] [--profile NAME] [--docker-network NETWORK] [--traefik-url URL]`
- `homesrvctl app init <hostname> [--template static|static-api|placeholder|node|python|jekyll] [--force] [--dry-run] [--json] [--profile NAME] [--docker-network NETWORK] [--traefik-url URL]`
- `homesrvctl up <hostname> [--dry-run] [--json]`
- `homesrvctl down <hostname> [--dry-run] [--json]`
- `homesrvctl restart <hostname> [--dry-run] [--json]`
- `homesrvctl list [--json]`
- `homesrvctl tui [--refresh-seconds FLOAT]`
- `homesrvctl cloudflared status [--json]`
- `homesrvctl cloudflared config-test [--json]`
- `homesrvctl cloudflared logs [--follow] [--json]`
- `homesrvctl cloudflared restart [--dry-run] [--json]`
- `homesrvctl cloudflared reload [--dry-run] [--json]`
- `homesrvctl validate [--json]`
- `homesrvctl doctor <hostname> [--json]`

## Notes

- `domain add` uses the Cloudflare DNS API to manage apex and wildcard records for the requested zone.
- `domain add`, `domain repair`, and `domain remove` support `--json` for machine-readable mutation results.
- all `--json` commands include a top-level `schema_version` so automation can pin to a known output shape.
- `config init --json` reports whether the config file was created or overwritten.
- `config show` reports global config values and can also report the effective `docker_network` and `traefik_url` for a specific stack after stack-local overrides are applied.
- stack-local config may select a named routing profile with `profile`, and direct stack-local overrides still win over profile-provided values.
- `domain status` reports expected tunnel target, apex and wildcard DNS state, apex and wildcard `cloudflared` ingress state, whether a route is being shadowed by an earlier ingress rule, whether Cloudflare DNS is ambiguous or of the wrong type, whether coverage is apex-only or wildcard-only, and whether `homesrvctl domain repair` is likely to fix the current state automatically.
- `domain status` also reports routing context for the apex stack, including the default ingress target, effective ingress target, selected profile, and source attribution for the effective target.
- `domain status` now also surfaces non-fatal ingress warnings when the configured `cloudflared` ingress file contains risky wildcard precedence, including earlier wildcard rules that may shadow later hostnames or capture traffic intended for a narrower wildcard.
- Those ingress warnings now include direct remediation hints, such as moving a narrower rule above a broader wildcard or removing an unused catch-all rule.
- `cloudflared status` keeps those warnings advisory: the command stays healthy when the runtime is active and the ingress file is structurally valid, while still surfacing the warnings in text and JSON output.
- `list`, `domain status`, `validate`, and `doctor` support `--json` for machine-readable output.
- `up`, `down`, and `restart` support `--json` for machine-readable command results.
- `site init` and `app init` support `--json` for machine-readable scaffold results, including the selected template and rendered template-to-output mapping.
- `cloudflared status` reports the detected runtime mode, whether it is active, and the restart command when one is available.
- `tui` launches a terminal dashboard backed by the existing JSON commands for `list`, `cloudflared status`, and `validate`.
- The Textual app title is `Home Server Controller`, which is the human-readable product name for the terminal UI.
- `tui` now launches a Textual app; reinstall the package or refresh the local dev venv after upgrading so the new dependency is present.
- The JSON forms of `cloudflared status`, `validate`, and `doctor` stay quiet so they can be consumed directly by scripts and the terminal dashboard.
- The dashboard now uses a roomy warm-console layout with a full-width summary strip, a left control pane, a right detail pane, and a persistent command/status bar.
- After you run a stack action from the TUI, the focused stack detail pane keeps the last action result visible, including `doctor` checks and compose command results where available.
- The summary strip is informational only; the left control pane is the primary navigation surface.
- The left control pane groups a small `Tools` section above the larger `Stacks` section and uses a unified vertical cursor.
- TUI navigation uses `tab`, arrow keys, or `w`/`s` to move through the control pane.
- When a stack is focused, `a` opens a small Textual template picker for `app init`, and the scaffold result stays visible in the stack detail pane after the prompt completes.
- The TUI now includes a `Config` tool item that renders the base `config show` output, and focused stack details also surface the effective per-stack config derived from `config show --stack`.
- Focused apex stacks now also surface `domain status` detail in the TUI, including overall state, repairability, coverage issues, and suggested repair command when available.
- Focused apex stacks can now run `domain repair` from the TUI with `p`, using the same CLI mutation path underneath and surfacing the result back in the stack pane.
- Focused apex stacks can now also confirm `domain add` with `n` and `domain remove` with `m` through a small modal prompt before the mutation runs.
- Focused stacks can also open a guided action menu with `Enter` or `o`, which lists the currently available stack actions and apex-domain actions for the selected hostname.
- When the `Cloudflared` tool is focused, the TUI can run `config-test` with `c`, `reload` with `l`, and `restart` with `k`, and the detail pane keeps the last tool result visible.
- When a stack is focused in the control pane, the TUI supports `site init` with `i`, and can run `doctor`, `up`, `restart`, and `down` for the selected hostname with `g`, `u`, `t`, and `x`.
- `cloudflared config-test` prefers `cloudflared tunnel ingress validate --config ...` when the binary is available and falls back to structural YAML/ingress validation otherwise.
- `cloudflared status` now also surfaces non-fatal config warnings when the ingress file is structurally valid but risky, such as an earlier wildcard rule that may shadow a later hostname rule or capture traffic intended for a narrower wildcard.
- `cloudflared logs` prints the right `journalctl` or `docker logs` command for the detected runtime and supports `--follow` plus `--json`.
- `cloudflared restart` also supports `--json` for automation-friendly dry-run and failure reporting.
- `cloudflared reload` is available when the detected runtime exposes a safe reload command; today that is primarily a systemd capability check rather than a guaranteed cross-runtime feature.
- `cloudflared config-test` now reports non-fatal warnings for risky ingress ordering even when the config is otherwise valid.
- `doctor` now reports routing profile, default ingress target, and effective ingress target before the hostname-specific routing checks.
- `doctor` now also includes `cloudflared ingress warnings` when the ingress file is structurally valid but risky.
- `domain add` also reconciles apex and wildcard hostname entries in the configured `cloudflared` ingress file so new domains route locally to Traefik.
- `domain add`, `domain status`, and `domain repair` honor stack-local `traefik_url` overrides stored in `<stack>/homesrvctl.yml` for the apex hostname.
- `domain repair` converges apex and wildcard DNS records and matching `cloudflared` ingress entries to the expected state.
- `domain add` resolves the tunnel target from the local `cloudflared` tunnel configuration and does not depend on the active `cloudflared tunnel login` zone.
- `domain remove` removes apex and wildcard DNS records and matching `cloudflared` ingress entries for the requested zone.
- pass `--restart-cloudflared` to have domain-changing commands restart `cloudflared` automatically when a supported runtime is detected
- without that flag, restart `cloudflared` manually after ingress changes
- `site init` and `app init` generate Traefik-safe router and service identifiers from the hostname.
- All generated Compose files join the external Docker network configured in `docker_network`.
- `site init` and `app init` can write stack-local `homesrvctl.yml` overrides for `docker_network` and `traefik_url`.
- `site init` and `app init` can also write a stack-local `profile` selection when you pass `--profile`.
- `app init --template static` now generates a real boring-static-website scaffold with nginx, `html/index.html`, `html/favicon.svg`, `html/assets/css/main.css`, `html/assets/js/main.js`, `html/assets/images/`, and a small generated README instead of the old placeholder stub.
- `app init --template static-api` now generates a two-service scaffold with a static nginx site plus a small Python API routed on `/api` behind the same hostname.
- The `node` app template now generates a runnable multi-file scaffold with `docker-compose.yml`, `Dockerfile`, `package.json`, `.env.example`, and `src/server.js`.
- The `python` app template now generates a runnable multi-file scaffold with `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `.env.example`, and `app/main.py`.
- The `jekyll` app template now generates a stack-local `site/` source tree plus a Dockerized Jekyll-to-nginx build baseline intended for manual adoption of an existing Jekyll site.
- To adopt an existing Jekyll repo, scaffold `--template jekyll`, copy the repo contents into `site/`, keep the generated `docker-compose.yml` and `Dockerfile`, then run `docker compose up --build`.
- The `node` and `python` app templates now include a basic container healthcheck that probes the generated root endpoint on the app’s internal port.
- The `node` and `python` app templates now expose a dedicated `/healthz` endpoint, and the generated healthchecks probe that endpoint instead of the user-facing root response.
- The generated `node` and `python` app READMEs now include explicit first-run steps for `docker compose up --build`, health verification, and when you actually need a `.env` file.
- Scaffold regression tests now assert that the rendered `node` and `python` artifacts stay internally consistent across ports, healthchecks, and rendered template manifests.
- The generated Dockerfiles now use slightly more realistic defaults: the Node scaffold installs runtime dependencies, and the Python scaffold sets the standard runtime environment flags before installing requirements.
- The generated `node` and `python` sources now document and implement a clearer runtime baseline: `GET /`, `GET /healthz`, explicit environment-variable inputs, and `405` responses for unsupported methods.
- The generated `node` and `python` `.env.example` files now include only real runtime overrides used by the scaffolded apps, instead of extra metadata-style keys.
