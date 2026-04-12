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
- inspecting the configured Cloudflare Tunnel reference and resolved tunnel UUID
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

That is the current shipped model. On a fresh Raspberry Pi, installing `homesrvctl` today gives you assessment, domain lifecycle, scaffolding, and operational controls for an already-built platform. It does not yet provision Docker, Traefik, `cloudflared`, or the initial tunnel for you.

## Long-Term Bootstrap Direction

The long-term direction is to make a fresh Pi first run capable of bringing up the whole platform instead of assuming it already exists.

Planned product direction:

- first bootstrap target: Debian-family Raspberry Pi OS with `apt` and `systemd`
- one shared host tunnel, not one tunnel per app
- Traefik remains the local ingress router
- Cloudflare API token is the primary bootstrap auth path
- browser-login-based setup may come later, but is not the first target

Desired long-term first-run outcome:

- install `homesrvctl`
- run a bootstrap workflow
- end with Docker, Compose, Traefik, `cloudflared`, shared directories, service/group wiring, a Cloudflare tunnel, and a ready `homesrvctl` config
- then use `domain add`, `site init`, `app init`, and `up` without separate manual Cloudflare dashboard setup

Current shipped step in that direction:

- `homesrvctl bootstrap assess` now reports whether the host looks fresh, partial, ready, or unsupported relative to the first bootstrap target
- `homesrvctl bootstrap tunnel` can now create or reuse the shared Cloudflare tunnel and write local bootstrap tunnel material when the target path is writable and local credentials are available for safe reuse
- `homesrvctl bootstrap runtime` can now install the Debian-family host runtime baseline for the first target: Docker Engine, Docker Compose, `cloudflared`, the shared `homesrvctl` group and directories, the external Docker network, and the baseline Traefik runtime
- `homesrvctl bootstrap wiring` can now converge the shared `cloudflared` config path, migrate local tunnel credentials into `/srv/homesrvctl/cloudflared`, install the needed systemd unit or override, and enable the service under the shared-group model
- `homesrvctl bootstrap validate` now reports whether the current host matches the completed shipped bootstrap baseline and is ready for first stack creation plus domain onboarding

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
- Tunnel inspection: `https://github.com/Broda/homesrvctl/wiki/Tunnel-Inspection`
- Terminal dashboard: `https://github.com/Broda/homesrvctl/wiki/Terminal-Dashboard`
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
cloudflared_config: /srv/homesrvctl/cloudflared/config.yml
cloudflare_api_token: ""
```

Existing installs remain non-breaking: `homesrvctl` continues to honor whatever explicit `cloudflared_config` path is already stored in your config file.

The first-class shared setup model now uses:

- config: `/srv/homesrvctl/cloudflared/config.yml`
- tunnel credentials JSON: `/srv/homesrvctl/cloudflared/<tunnel-id>.json`
- ownership: `root:homesrvctl`
- permissions:
  - directory `750`
  - files `640`

The tunnel credentials JSON is secret material. It should not be world-readable. If you want unprivileged `homesrvctl` tunnel inspection, grant access through the dedicated `homesrvctl` group rather than broad file permissions.

The top-level `docker_network` and `traefik_url` values are the implicit default routing profile for stacks that do not opt into anything else.

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
If you want API-backed tunnel inspection via `homesrvctl tunnel status` and API-backed tunnel resolution when no local UUID is available, the token must also be able to read the relevant Cloudflare Tunnel in the owning account.
Tunnel resolution is now explicit: local UUID from `tunnel_name` or the local `cloudflared` config first, then account-scoped API lookup when credentials context exists. There is no `cloudflared tunnel info` fallback.

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

Routing model and precedence:

1. Global defaults come from the top-level `docker_network` and `traefik_url` config keys.
2. A stack may opt into a named routing profile by writing `profile: <name>` in its stack-local `homesrvctl.yml`, or by passing `--profile` to `site init` or `app init`.
3. Stack-local `docker_network` and `traefik_url` keys remain first-class one-off overrides and win over the selected profile when both are present.

Examples:

All-default stack, no stack-local config needed:

```yaml
# no /srv/homesrvctl/sites/example.com/homesrvctl.yml file
```

Stack that opts into a named profile:

```yaml
profile: edge
```

Stack that uses a profile plus one direct one-off override:

```yaml
profile: edge
traefik_url: http://localhost:9001
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
homesrvctl bootstrap assess
sudo homesrvctl bootstrap runtime
homesrvctl bootstrap tunnel --account-id <cloudflare-account-id>
sudo homesrvctl bootstrap wiring
homesrvctl bootstrap validate
homesrvctl
homesrvctl tui
homesrvctl tunnel status
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
homesrvctl bootstrap assess --json
homesrvctl bootstrap runtime --dry-run --json
homesrvctl bootstrap tunnel --account-id <cloudflare-account-id> --json
homesrvctl bootstrap wiring --dry-run --json
homesrvctl bootstrap validate --json
homesrvctl tunnel status --json
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
- `homesrvctl bootstrap assess [--path PATH] [--json]`
- `homesrvctl bootstrap runtime [--path PATH] [--operator-user USER] [--force] [--dry-run] [--json]`
- `homesrvctl bootstrap tunnel [--path PATH] [--account-id ACCOUNT_ID] [--name NAME] [--force] [--json]`
- `homesrvctl bootstrap wiring [--path PATH] [--force] [--dry-run] [--json]`
- `homesrvctl bootstrap validate [--path PATH] [--json]`
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
- `homesrvctl cloudflared setup [--json]`
- `homesrvctl cloudflared config-test [--json]`
- `homesrvctl cloudflared logs [--follow] [--json]`
- `homesrvctl cloudflared restart [--dry-run] [--json]`
- `homesrvctl cloudflared reload [--dry-run] [--json]`
- `homesrvctl validate [--json]`
- `homesrvctl doctor <hostname> [--json]`

## Notes

- `domain add` uses the Cloudflare DNS API to manage apex and wildcard records for the requested zone.
- `domain add`, `domain repair`, and `domain remove` support `--json` for machine-readable mutation results.
- `domain add`, `domain repair`, and `domain remove` now preflight local ingress mutation safety before writing DNS: if the configured `cloudflared` config path is not writable by the current user, or if an active systemd service is pointed at a different config file, the command fails early with setup guidance instead of making a partial DNS-only change.
- `bootstrap assess` is still the assessment-only host-readiness command for the current Debian-family Pi bootstrap target.
- `bootstrap runtime` is the host-baseline mutation command for the current bootstrap target. It is meant to run as root, supports `--dry-run` and `--json`, installs Docker Engine plus the Docker Compose plugin and `cloudflared`, creates the shared `homesrvctl` group and `/srv/homesrvctl` layout, creates the external Docker network, and starts the baseline Traefik runtime from `/srv/homesrvctl/traefik/docker-compose.yml`.
- `bootstrap runtime` defaults the operator account from `SUDO_USER` or `USER` when available and adds that user to the `homesrvctl` and `docker` groups.
- `bootstrap tunnel` is the first mutating bootstrap slice: it creates a locally managed Cloudflare tunnel when needed, reuses a safely recoverable local tunnel when credentials already exist, writes bootstrap credentials plus a minimal `cloudflared` config, and normalizes `tunnel_name` in the main config to the tunnel UUID.
- `bootstrap tunnel` currently requires `--account-id` unless the current `cloudflared` credentials file is already readable and can supply the account ID.
- `bootstrap wiring` is the shared-group cloudflared convergence command. It can create the main config when missing, normalize `cloudflared_config` to `/srv/homesrvctl/cloudflared/config.yml`, migrate tunnel credentials into the shared path, install the systemd unit or override needed for the active host, and enable the `cloudflared` service.
- In the shared-group model, `/srv/homesrvctl/cloudflared/config.yml` is intended to be `root:homesrvctl` and group-writable so trusted operators can update ingress, while the tunnel credentials JSON remains secret material and should stay non-public.
- `bootstrap tunnel` needs Cloudflare tunnel-write capability in addition to the existing DNS-oriented token permissions. The current practical token set is:
  - `Zone: Read`
  - `DNS: Edit`
  - `Account: Cloudflare Tunnel Read` for inspection
  - `Account: Cloudflare Tunnel Edit` for bootstrap tunnel provisioning
- `bootstrap wiring` expects tunnel credentials to already exist locally. If they do not, run `bootstrap tunnel` first or point the config at an existing local cloudflared setup before wiring the service.
- `bootstrap validate` is the final shipped bootstrap check. It composes `bootstrap assess`, the existing host `validate` checks, `tunnel status`, and the shared-group `cloudflared` setup state into one explicit `ready` / `not_ready` / `unsupported` result for the current host.
- `bootstrap validate` is intentionally stricter than `cloudflared status`: a setup state of `partial` still means the host is not fully bootstrapped yet because account-scoped tunnel inspection is not available from the current user.
- Running `homesrvctl` with no arguments now launches the same Textual dashboard as `homesrvctl tui`.
- all `--json` commands include a top-level `schema_version` so automation can pin to a known output shape.
- `config init --json` reports whether the config file was created or overwritten.
- `config show` reports global config values and can also report the effective `docker_network` and `traefik_url` for a specific stack after stack-local overrides are applied.
- stack-local config may select a named routing profile with `profile`, and direct stack-local overrides still win over profile-provided values.
- `domain status` reports expected tunnel target, apex and wildcard DNS state, apex and wildcard `cloudflared` ingress state, whether a route is missing, duplicated, shadowed by an earlier ingress rule, or pointed at the wrong target, whether Cloudflare DNS is missing, of the wrong type, pointed at the wrong target, or ambiguous because multiple conflicting records exist, whether coverage is apex-only or wildcard-only, and whether `homesrvctl domain repair` is likely to fix the current state automatically.
- `domain status` also reports routing context for the apex stack, including the default ingress target, effective ingress target, selected profile, and source attribution for the effective target.
- `domain status` now also surfaces normalized ingress issues from the configured `cloudflared` file, separating blocking states from advisory wildcard-precedence risks.
- Blocking ingress issues include duplicate exact hostname entries and exact hostnames shadowed by an earlier broader rule; advisory issues keep direct remediation hints for risky wildcard ordering.
- `cloudflared status` keeps advisory ingress issues non-fatal while failing on a narrow set of blocking semantic-danger states, and the same normalized severity is available in text and JSON output.
- `list`, `domain status`, `validate`, and `doctor` support `--json` for machine-readable output.
- `up`, `down`, and `restart` support `--json` for machine-readable command results.
- `site init` and `app init` support `--json` for machine-readable scaffold results, including the selected template and rendered template-to-output mapping.
- `cloudflared status` reports the detected runtime mode, whether it is active, the restart command when one is available, and a setup-alignment report for the configured `cloudflared_config` path and tunnel credentials JSON.
- `cloudflared setup` assesses whether `homesrvctl` and the active runtime are pointed at the same config path, whether ingress mutations are safe, whether account-scoped tunnel inspection is available from the current user, and prints exact shared-group migration commands when a systemd override or credential/config migration is needed.
- The first-class setup/repair path is systemd-focused. Docker and bare-process runtimes still get status visibility, but setup repair remains advisory there.
- `homesrvctl` does not prompt for `sudo` inside the CLI or TUI. When setup changes require elevated privileges, it prints the exact commands to run manually.
- The first-class setup model uses a dedicated `homesrvctl` Unix group so `cloudflared` and unprivileged operators can share read access to the tunnel credentials JSON without making it public.
- `tui` launches a terminal dashboard backed by the existing JSON commands for `list`, `config show`, `tunnel status`, `cloudflared status`, `validate`, and `bootstrap assess`.
- A bare `homesrvctl` invocation now enters that same TUI path by default; keep using explicit subcommands for non-TUI automation.
- The Textual app title is `Home Server Controller`, which is the human-readable product name for the terminal UI.
- `tui` now launches a Textual app; reinstall the package or refresh the local dev venv after upgrading so the new dependency is present.
- `tui` requires an interactive terminal on both stdin and stdout, and it assumes the local machine has the same runtime access as the CLI commands it launches: Docker where stack actions are used, local config-file access, and local `cloudflared` runtime access where `cloudflared` tools are used.
- The JSON forms of `cloudflared status`, `validate`, and `doctor` stay quiet so they can be consumed directly by scripts and the terminal dashboard.
- The dashboard now uses a roomy warm-console layout with a full-width summary strip, a left control pane, a right detail pane, and a persistent command/status bar.
- After you run a stack action from the TUI, the focused stack detail pane keeps the last action result visible, including `doctor` checks and compose command results where available.
- The summary strip is informational only; the left control pane is the primary navigation surface.
- The left control pane groups a small `Tools` section above the larger `Stacks` section and uses a unified vertical cursor.
- TUI navigation uses `tab`, arrow keys, or `w`/`s` to move through the control pane.
- The TUI also accepts mouse input: clicking a control row, summary card, modal option, or detail action button is equivalent to selecting it with the keyboard, and mouse and keyboard selection share the same highlighted row. Mouse support is additive — every click target is also reachable by keyboard — and is quietly ignored when the host terminal does not report mouse events.
- The TUI now exposes a global stack-creation flow with `b` or the `Create` detail button, so operators can scaffold a brand-new hostname without first creating a placeholder row in the CLI.
- The guided create flow stays layered over the existing `site init` and `app init` commands, including hostname entry, create-mode selection, optional app-template selection, optional `profile` / `docker_network` / `traefik_url` inputs, and overwrite confirmation when the scaffold path already exists.
- When `Create` is used for a bare apex domain like `example.com`, the TUI now runs `domain add` automatically before scaffold creation so apex onboarding and stack creation happen in one guided path.
- When `Create` is used for a subdomain like `app.example.com`, the TUI only scaffolds the stack and does not try to onboard the apex domain automatically.
- When a stack is focused, `a` opens a small Textual template picker for `app init`, and the scaffold result stays visible in the stack detail pane after the prompt completes.
- The TUI now includes a `Config` tool item that renders the base `config show` output, and focused stack details also surface the effective per-stack config derived from `config show --stack`.
- The TUI now also includes a `Tunnel` tool item that renders the current `tunnel status` output, including the configured reference, resolved UUID, resolution source, API tunnel status when available, and a non-alarming note when account inspection is unavailable only because the current user cannot read the local credentials JSON.
- The TUI now also includes a `Bootstrap` tool item and summary card that surface the current `bootstrap assess` result, including host support, bootstrap state, issues, and next-step guidance for the planned fresh-host bootstrap target.
- Focused `Config`, `Tunnel`, and `Cloudflared` tool items can now open guided tool menus with `Enter` or `o`, so low-frequency global actions stay discoverable without replacing the underlying CLI verbs.
- When the `Cloudflared` tool is focused, the TUI now also exposes a `Fix Setup` action that runs `cloudflared setup` and keeps the generated repair guidance visible in the detail pane.
- The guided `Config` tool flow can now run the default-path `config init` path from inside the TUI, and it asks for overwrite confirmation only when the existing config file would need `--force`.
- Focused apex stacks now also surface `domain status` detail in the TUI, including overall state, repairability, coverage issues, and suggested repair command when available.
- Focused apex stacks can now run `domain repair` from the TUI with `p`, using the same CLI mutation path underneath and surfacing the result back in the stack pane.
- Focused apex stacks can now also confirm `domain add` with `n` and `domain remove` with `m` through a small modal prompt before the mutation runs.
- Focused stacks can also open a guided action menu with `Enter` or `o`, which lists the currently available stack actions and apex-domain actions for the selected hostname.
- When the `Cloudflared` tool is focused, the TUI can run `config-test` with `c`, `reload` with `l`, and `restart` with `k`, and the detail pane keeps the last tool result visible.
- The guided `Cloudflared` tool flow now also covers `cloudflared logs`, including a choice between standard and `--follow` guidance, and the suggested runtime log command stays visible in the detail pane after the prompt completes.
- When a stack is focused in the control pane, the TUI supports `site init` with `i`, and can run `doctor`, `up`, `restart`, and `down` for the selected hostname with `g`, `u`, `t`, and `x`.
- `cloudflared config-test` prefers `cloudflared tunnel ingress validate --config ...` when the binary is available and falls back to structural YAML/ingress validation otherwise.
- `cloudflared status` now also surfaces non-fatal config warnings when the ingress file is structurally valid but risky, such as an earlier wildcard rule that may shadow a later hostname rule or capture traffic intended for a narrower wildcard.
- `cloudflared status` now also reports whether the configured `cloudflared` path is aligned with the active systemd unit and whether `homesrvctl` can safely mutate ingress from the current account.
- `cloudflared logs` prints the right `journalctl` or `docker logs` command for the detected runtime and supports `--follow` plus `--json`.
- `cloudflared restart` also supports `--json` for automation-friendly dry-run and failure reporting.
- `cloudflared reload` is available when the detected runtime exposes a safe reload command; today that is primarily a systemd capability check rather than a guaranteed cross-runtime feature.
- `cloudflared config-test` now reports normalized ingress issues in JSON and fails on blocking semantic-danger states while keeping broader wildcard-precedence risks advisory.
- `doctor` now reports routing profile, default ingress target, and effective ingress target before the hostname-specific routing checks.
- `doctor` now also includes normalized `cloudflared` ingress issue severity so advisory risks remain visible without being flattened into hard failures.
- `domain add` also reconciles apex and wildcard hostname entries in the configured `cloudflared` ingress file so new domains route locally to Traefik.
- `domain add`, `domain status`, and `domain repair` honor stack-local `traefik_url` overrides stored in `<stack>/homesrvctl.yml` for the apex hostname.
- `domain repair` converges apex and wildcard DNS records and matching `cloudflared` ingress entries to the expected state.
- `domain add` resolves the tunnel target from the local `cloudflared` tunnel configuration and does not depend on the active `cloudflared tunnel login` zone.
- `domain remove` removes apex and wildcard DNS records and matching `cloudflared` ingress entries for the requested zone.
- pass `--restart-cloudflared` to have domain-changing commands restart `cloudflared` automatically when a supported runtime is detected
- without that flag, restart `cloudflared` manually after ingress changes
- The TUI creation surface is now considered complete for common local onboarding when it can:
  - create a static site stack
  - create an app stack from a shipped template
  - onboard an apex domain
  - inspect resulting routing and domain state
  - run first `up`, `doctor`, `domain repair`, and related verification actions
- Some creation inputs remain intentionally CLI-first for now:
  - stack scaffold `--dry-run`
  - explicit scaffold `--force` as a first-choice prompt, though the TUI does surface overwrite confirmation when files already exist
- Some flows remain intentionally out of scope for the TUI:
  - bulk or multi-site creation
  - remote creation against another host
  - generalized form-style config editing
- `site init` and `app init` generate Traefik-safe router and service identifiers from the hostname.
- All generated Compose files join the external Docker network configured in `docker_network`.
- `site init` and `app init` can write stack-local `homesrvctl.yml` overrides for `docker_network` and `traefik_url`.
- `site init` and `app init` can also write a stack-local `profile` selection when you pass `--profile`.
- `site init` remains the narrow two-file static scaffold for quick hostname bootstrapping, while `app init --template static` is the richer static-site app baseline with nginx starter assets and operator guidance.
- `app init --template static` now generates a real boring-static-website scaffold with nginx, `html/index.html`, `html/favicon.svg`, `html/assets/css/main.css`, `html/assets/js/main.js`, `html/assets/images/`, and a small generated README instead of the old placeholder stub.
- `app init --template static-api` now generates a two-service scaffold with a static nginx site plus a small Python API routed on `/api` behind the same hostname, and includes a root `.dockerignore` because the API image builds from the stack root.
- The `node` app template now generates a runnable multi-file scaffold with `docker-compose.yml`, `Dockerfile`, `package.json`, `.env.example`, and `src/server.js`.
- The `python` app template now generates a runnable multi-file scaffold with `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `.env.example`, and `app/main.py`.
- The `jekyll` app template now generates a stack-local `site/` source tree plus a Dockerized Jekyll-to-nginx build baseline intended for manual adoption of an existing Jekyll site.
- To adopt an existing Jekyll repo, scaffold `--template jekyll`, copy the repo contents into `site/`, keep the generated `docker-compose.yml` and `Dockerfile`, then run `docker compose up --build`.
- The shipped app-template catalog now drives CLI validation, TUI template selection, rendered-template manifests, and release packaging checks from one module so those surfaces do not drift independently.
- The `node` and `python` app templates now include a basic container healthcheck that probes the generated root endpoint on the app’s internal port.
- The `node` and `python` app templates now expose a dedicated `/healthz` endpoint, and the generated healthchecks probe that endpoint instead of the user-facing root response.
- The generated `node` and `python` app READMEs now include explicit first-run steps for `docker compose up --build`, health verification, and when you actually need a `.env` file.
- Scaffold regression tests now assert that the rendered `node` and `python` artifacts stay internally consistent across ports, healthchecks, and rendered template manifests.
- Scaffold artifact-coherence coverage now also locks down the shipped `site init`, `static`, `static-api`, `placeholder`, and `jekyll` scaffolds so template manifests, healthcheck expectations, and guidance do not drift silently.
- The generated Dockerfiles now use slightly more realistic defaults: the Node scaffold installs runtime dependencies, and the Python scaffold sets the standard runtime environment flags before installing requirements.
- The generated `node` and `python` sources now document and implement a clearer runtime baseline: `GET /`, `GET /healthz`, explicit environment-variable inputs, and `405` responses for unsupported methods.
- The generated `node` and `python` `.env.example` files now include only real runtime overrides used by the scaffolded apps, instead of extra metadata-style keys.
