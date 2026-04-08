# Roadmap

`homesrvctl` is a small operator-focused CLI for managing self-hosted sites behind Cloudflare Tunnel, Traefik, and Docker Compose. This roadmap is organized as milestones so the next slices are easier to reason about and easier to ship intentionally.

## Milestone 0: Completed Foundation

Status: shipped

This milestone is already done and serves as the current project baseline.

### CLI foundation

- Config initialization exists.
- Config inspection exists via `config show`.
- Stack scaffolding exists for:
  - `site init`
  - `app init --template placeholder`
  - `app init --template node`
  - `app init --template python`
- Deploy lifecycle exists for:
  - `up`
  - `down`
  - `restart`
  - `list`
  - `doctor`
  - `validate`

### Domain lifecycle

- Domain lifecycle commands exist for:
  - `domain add`
  - `domain status`
  - `domain repair`
  - `domain remove`
- DNS management is API-based through Cloudflare.
- `cloudflared` ingress reconciliation is built into domain mutation flows.
- Domain status reports:
  - `ok`
  - `partial`
  - `misconfigured`
  - repair hints
  - shadowed ingress rules
  - ambiguous DNS state
  - apex-only versus wildcard-only coverage issues

### Cloudflared operations

- Runtime detection exists for:
  - `systemd`
  - Docker-managed `cloudflared`
  - unmanaged process mode
- Operator commands exist for:
  - `cloudflared status`
  - `cloudflared restart`
  - `cloudflared reload`
  - `cloudflared logs`
  - `cloudflared config-test`

### Machine-readable output

- JSON output exists for:
  - `config init`
  - `config show`
  - `site init`
  - `app init`
  - `up`
  - `down`
  - `restart`
  - `list`
  - `validate`
  - `doctor`
  - `domain add`
  - `domain status`
  - `domain repair`
  - `domain remove`
  - `cloudflared status`
  - `cloudflared restart`
  - `cloudflared logs`
  - `cloudflared config-test`
- All JSON output uses a shared top-level `schema_version`.

### Routing and stack-local overrides

- Stack-local `homesrvctl.yml` overrides exist for:
  - `profile`
  - `docker_network`
  - `traefik_url`
- Scaffold commands can write stack-local overrides.
- Domain and doctor flows honor apex stack `traefik_url` overrides.
- `domain status` and `doctor` now explain routing context explicitly for the inspected hostname.

### Project and release infrastructure

- Public repo cleanup is done.
- CI is in place and green.
- GitHub Releases are automated.
- TestPyPI publishing is automated.
- PyPI publishing is automated.
- Wiki exists and is linked from the README.
- Package is published publicly as `homesrvctl`.

## Milestone 1: Domain and Routing Hardening

Status: next

Goal: make non-default routing setups and ambiguous domain state easier to understand and safer to operate.

### 1.1 Refresh status and repair diagnostics

Status: in progress

Tasks:
- Tighten non-JSON error paths so they stay short and actionable.
- Make ambiguous state messages more explicit about what `repair` can fix automatically.
- Make ambiguous state messages more explicit about what requires manual cleanup.
- Review domain mutation failure paths for wording consistency across:
  - `add`
  - `status`
  - `repair`
  - `remove`

Subtasks:
- Audit `domain_cmd.py` error messages for duplicate phrasing or inconsistent terminology.
- Standardize “repairable” versus “manual fix required” wording.
- Ensure DNS conflict messages distinguish:
  - missing record
  - wrong type
  - wrong target
  - multiple conflicting records
- Ensure ingress conflict messages distinguish:
  - missing entry
  - duplicate entry
  - shadowed entry
  - invalid fallback ordering

### 1.2 Formalize the routing-profile model

Status: in progress

Goal: evolve from two standalone override keys into a coherent routing model that can grow without turning the CLI into a pile of flags.

Tasks:
- Define what a routing profile is in global config.
- Define how a stack opts into a non-default routing profile.
- Decide how profile selection interacts with direct per-stack overrides.
- Decide whether direct override keys remain first-class or become an escape hatch.

Subtasks:
- Document the current implicit default profile:
  - one shared `traefik_url`
  - one shared `docker_network`
- Design a profile shape such as:
  - `profiles.default`
  - `profiles.internal`
  - `profiles.edge-b`
- Define stack-local config shape for:
  - `profile`
  - optional direct override values
- Decide precedence order between:
  - global defaults
  - named profile values
  - stack-local direct overrides
- Add documentation examples for:
  - all-default stack
  - stack with named profile
  - stack with one-off override

Completed in this milestone so far:
- Global config now supports named `profiles`.
- Stack-local `homesrvctl.yml` now supports `profile`.
- `site init` and `app init` support `--profile`.
- Direct stack-local overrides still win over selected profile values.
- `cloudflared status` and `cloudflared config-test` now surface non-fatal ingress shadowing warnings for risky wildcard ordering.
- `domain status` and `doctor` now surface the same non-fatal ingress shadowing warnings when they affect hostname troubleshooting.
- `cloudflared reload` now exists when the detected runtime provides a safe reload command.
- Mixed-routing regression coverage now includes:
  - network-only overrides
  - default-versus-overridden stacks side by side
  - domain mutation behavior across mixed routing setups

### 1.3 Support more than one ingress target cleanly

Status: deferred

Tasks:
- Revisit richer multi-ingress support only if real operator use cases outgrow the current profile-and-override model.
- Keep the current routing model stable unless additional ingress classes clearly justify more product surface.

Subtasks:
- Decide whether additional ingress targets belong in:
  - named routing profiles
  - direct stack-local overrides only
- Revisit whether domain and doctor flows need richer ingress-class reporting beyond the current routing context.
- Add more tests only if a new ingress model is actually introduced.

Current baseline:
- Global profiles plus stack-local `traefik_url` overrides already support one-off alternate ingress targets.
- `domain status`, `doctor`, and `config show` already report the effective routing target and its source.

### 1.4 Broaden non-default routing tests

Status: planned

Tasks:
- Add product-focused tests for non-default routing setups.
- Keep local verification aligned with CI as the routing matrix grows.

Subtasks:
- Add tests for alternate `docker_network` only.
- Add tests for alternate `traefik_url` only.
- Add tests for both overrides together.
- Add tests for stacks with no override file next to stacks with overrides.
- Add tests for domain commands against mixed default-versus-overridden stacks.
- Add tests for JSON output so effective routing data stays stable.

## Milestone 2: Operator UX and Config Safety

Status: next

Goal: make the tool safer to use interactively and easier to reason about when local config gets more complex.

### 2.1 Improve `cloudflared` config safety messaging

Status: planned

Tasks:
- Add more domain-level diagnostics for unsafe or ambiguous `cloudflared` config states.
- Keep parser errors concrete and remediation-oriented.

Subtasks:
- Detect more cases where one ingress rule unintentionally captures another hostname.
  Current coverage includes broad wildcard rules that may capture traffic intended for a narrower wildcard.
- Improve guidance around wildcard precedence.
  Current warnings now include direct fix hints for reordering or narrowing risky wildcard rules.
- Improve messaging when the config file is valid YAML but semantically unsafe.
- Decide whether `cloudflared status` should surface config warnings directly.
  Current behavior keeps structurally valid ingress warnings advisory in `cloudflared status`.

### 2.2 Explore safe reload behavior

Status: planned

Tasks:
- Decide whether `cloudflared reload` is safe and worth exposing.
- Keep `restart` as the current baseline unless reload is clearly reliable.

Subtasks:
- Check whether systemd-managed `cloudflared` supports a meaningful reload path.
- Check whether Docker-managed `cloudflared` has a safe reload equivalent.
- Decide whether reload should:
  - be a standalone command
  - be used automatically by domain mutation flows
  - remain unsupported
- Document the operator tradeoff if reload is not reliable across runtimes.

### 2.3 Expand config introspection

Status: mostly shipped

Tasks:
- Keep the current effective-config surface stable and understandable.
- Reopen this area only if new routing or TUI work reveals a real visibility gap.

Subtasks:
- Extend `config show --json` only if additional consumers genuinely need more detail.
- Keep stack-focused inspection aligned across:
  - `config show --stack`
  - `domain status`
  - `doctor`
- Preserve clear separation between:
  - global values
  - inherited defaults
  - stack-local overrides

Current baseline:
- `config show` exists in text and JSON forms.
- `config show --stack` reports effective routing values and their sources.
- `domain status` and `doctor` already surface routing context for the inspected hostname.

### 2.4 Keep command surfaces convergent and predictable

Status: ongoing

Tasks:
- Preserve a simple operator model where one command does the obvious thing.
- Avoid adding overlapping flags unless they clearly improve safety or automation.
- Keep command naming consistent across lifecycle flows.

Subtasks:
- Review new flag proposals against existing domain and deploy verbs.
- Prefer convergent/idempotent mutation behavior on reruns.
- Add regression tests whenever a command gains:
  - a new runtime branch
  - a new output mode
  - a new mutation side effect

## Milestone 3: Scaffold and Template Expansion

Status: next

Goal: make `app init` more useful without turning `homesrvctl` into a full framework generator.

### 3.1 Mature the existing templates

Status: planned

Tasks:
- Review the current `node` and `python` scaffolds for the minimum polish needed to feel intentional.
- Keep generated apps simple, but runnable and understandable.

Subtasks:
- Review whether generated READMEs are consistent in structure.
  Current baseline: generated `node` and `python` READMEs now both document endpoints, runtime inputs, and first-run behavior in the same structure.
- Review whether `.env.example` files explain only what users actually need.
  Current baseline: generated `node` and `python` READMEs now include explicit first-run and healthcheck guidance, and `.env.example` files now say they are optional unless you need overrides.
  Current baseline: generated `node` and `python` `.env.example` files now include only runtime variables that the scaffolded apps actually read.
- Review whether Dockerfiles use reasonable defaults without too much magic.
  Current baseline: the Node scaffold now installs runtime dependencies during the image build, and the Python scaffold now sets standard runtime environment flags before installing requirements.
- Review whether generated source files include only the minimum useful comments.
  Current baseline: scaffold regression coverage now checks rendered template manifests plus port and healthcheck consistency across generated `node` and `python` artifacts.
  Current baseline: generated `node` and `python` app templates include container healthchecks against their default root endpoints.
  Current baseline: generated `node` and `python` sources now expose a dedicated `/healthz` endpoint for container healthchecks.
  Current baseline: generated `node` and `python` sources now return explicit `405` responses for unsupported methods instead of falling back to runtime-specific defaults.

### 3.2 Add a “static app plus API” pattern

Status: planned

Goal: support a common self-hosted pattern where one hostname serves static assets and proxies to a small app service.

Current baseline:
- `app init --template static` now generates a real static-site scaffold with nginx, `html/index.html`, a placeholder favicon, basic asset folders, and a generated README.
- `app init --template static-api` now generates a first basic site-plus-API scaffold with a static nginx frontend and a small Python API on `/api`.

Tasks:
- Define the scope of a combined static-plus-app scaffold.
- Decide whether it should be a first-class app template.
  Current baseline: the first implementation is now a first-class `static-api` template.

Subtasks:
- Decide whether the scaffold should generate:
  - one service plus build output
  - two services behind Traefik
  - nginx plus app container
- Decide how much frontend structure belongs in scope.
- Decide whether the template should target:
  - Node
  - Python
  - runtime-agnostic layout
- Add template-specific tests if implemented.
  Current baseline: the template now has dedicated scaffold and JSON-output tests.

### 3.3 Decide the philosophy boundary for scaffolds

Status: shipped

Goal: keep `homesrvctl` focused on deployable hosting baselines rather than turning it into a general app generator.

Decision:
- A scaffold should provide the smallest useful deployable baseline for a hostname or app pattern.
- A scaffold may include:
  - Compose
  - minimal Dockerfile
  - minimal runtime entrypoint
  - basic static assets
  - small generated README guidance
  - healthchecks
- A scaffold should not include by default:
  - large framework setups
  - frontend build pipelines
  - databases
  - auth systems
  - migrations
  - production app architecture choices
  - opinionated deployment stacks beyond the local hosting baseline

Implications:
- Templates should stay easy to understand after generation.
- New templates should bias toward runtime-agnostic or minimal-runtime examples.
- If a template starts needing substantial framework-specific machinery, it should be treated as a separate design decision, not the default next scaffold.

Applied examples:
- `static` stays a plain nginx-backed website with basic assets.
- `static-api` stays a small two-service pattern rather than a frontend framework plus backend stack.
- `node` and `python` stay minimal runtime baselines rather than framework starters.

### 3.4 Keep template layout scalable

Status: ongoing

Tasks:
- Preserve the per-template directory layout under `homesrvctl/templates/app/`.
- Avoid regressing to flat template sprawl.

Subtasks:
- Keep template assets grouped under:
  - `placeholder/`
  - `node/`
  - `python/`
  - any future template directories
- Keep scaffold JSON metadata aligned with whatever template structure is shipped.

## Milestone 4: API Reliability and Cloudflare Coverage

Status: later

Goal: decide whether more Cloudflare interactions should move from CLI-assisted flows to API-managed flows.

### 4.1 Audit remaining CLI-dependent Cloudflare flows

Status: planned

Tasks:
- Review whether any remaining `cloudflared` CLI usage is fragile enough to justify API replacements.
- Keep the current hybrid model unless migration clearly reduces operator risk.

Subtasks:
- Inventory current CLI-dependent operations.
- Separate:
  - runtime/process control concerns
  - Cloudflare control-plane concerns
- Identify which flows are unreliable because of environment assumptions rather than API gaps.

### 4.2 Evaluate broader tunnel inspection or management coverage

Status: planned

Tasks:
- Review whether tunnel inspection should move further to the Cloudflare API.
- Avoid replacing stable local-runtime operations with API calls unless there is a real reliability win.

Subtasks:
- Evaluate whether tunnel target discovery should rely less on local `cloudflared` behavior.
- Evaluate whether tunnel metadata checks should be surfaced in a dedicated command.
- Decide whether tunnel-management work belongs in `homesrvctl` scope at all.

## Milestone 5: Terminal UI (Textual Migration)

Status: in progress

Goal: move `homesrvctl tui` to Textual before the current terminal dashboard grows much larger, while keeping the same CLI entrypoint and the same terminal-first operator model.

Migration policy:
- Textual is the planned long-term TUI implementation.
- The current `curses` dashboard is transitional and should be retired after the first Textual dashboard reaches parity.
- `homesrvctl tui` remains the public entrypoint throughout the migration.
- The first Textual implementation should continue consuming existing `--json` command output rather than introducing a new backend service.

### 5.1 Establish the Textual foundation

Status: in progress

Tasks:
- Keep the TUI in the main repo and same package.
- Make Textual the canonical implementation target for `homesrvctl tui`.
- Keep the Textual app as a terminal-first layer over the existing CLI rather than a new control plane.

Subtasks:
- Add Textual as a runtime dependency and document the packaging impact.
- Define the initial Textual structure under `homesrvctl/tui/`, including:
  - `app.py`
  - screen/view modules
  - widget modules
  - shared data/action helpers
- Keep the first implementation JSON-driven:
  - shell out to `homesrvctl ... --json`
  - only revisit direct Python integration if the JSON boundary becomes a maintenance problem
- Keep the TUI out of scope for:
  - browser-based UI work
  - remote multi-user access
  - long-lived background services

Current baseline:
- `homesrvctl tui` already exists in the main repo.
- The current implementation shells out to existing `--json` commands for:
  - `list`
  - `cloudflared status`
  - `validate`

### 5.2 Reach dashboard parity in Textual

Status: in progress

Tasks:
- Reproduce the current dashboard capabilities in Textual before removing the old renderer.
- Reuse existing status/reporting surfaces rather than inventing a new state model.

Subtasks:
- Recreate the current home screen summaries for:
  - stacks
  - `cloudflared`
  - validation state
- Recreate the current detail views for:
  - stacks
  - `cloudflared`
  - validation
- Recreate the current stack controls for the selected hostname:
  - `site init`
  - `doctor`
  - `up`
  - `restart`
  - `down`
- Recreate refresh behavior:
  - manual `r`
  - optional timed refresh via `--refresh-seconds`
- Keep the first Textual dashboard functionally equivalent before adding net-new TUI behavior.

Current baseline:
- The current dashboard already provides the parity target:
  - stack summary
  - `cloudflared` runtime/config summary
  - validation failure summary
  - section selection
  - focused detail panes
  - selected-stack actions
  - manual and timed refresh

### 5.3 Improve layout and theming with Textual

Status: in progress

Tasks:
- Use Textual to move beyond the compact curses layout and give the TUI a clearer long-term visual structure.
- Keep the interface dense and operator-focused rather than decorative.

Subtasks:
- Define a stable Textual layout with:
  - left summary/navigation pane
  - main detail pane
  - bottom status/action bar
- Define visual states for:
  - selected
  - success
  - warning
  - error
  - running/busy
- Preserve the existing keyboard model where it still makes sense, but allow Textual-specific polish where it improves clarity.
- Keep the theme intentional and readable on typical terminal backgrounds without introducing a second “brand system” separate from the CLI.

### 5.4 Add guided flows for common operations

Status: planned

Tasks:
- Make the common multi-step operations easier to run without memorizing command sequences.
- Keep the Textual app aligned with the existing CLI verbs and mutation behavior.

Subtasks:
- Add guided flows for:
  - domain add
  - site/app scaffold
  - stack up/down/restart
  - doctor
  - repair
- Decide how Textual prompts/screens should handle:
  - hostname
  - template selection
  - profile selection
  - routing overrides
  - restart/reload choices
- Keep all TUI-driven mutations understandable as ordinary `homesrvctl` operations underneath.

### 5.5 Make diagnostics explorable

Status: planned

Tasks:
- Turn the existing rich status output into something easier to inspect interactively.
- Preserve the current operator model where warnings and remediation hints remain explicit.

Subtasks:
 - Add detail views for:
  - effective config
  - domain status
  - doctor output
  - `cloudflared` status
 - Surface routing context clearly:
  - default target
  - effective target
  - profile
  - override source
 - Surface remediation hints directly for:
  - ingress warnings
  - domain repairability
  - config problems

### 5.6 Retire curses and keep the Textual TUI testable

Status: planned

Tasks:
- Remove the transitional curses implementation after the Textual dashboard reaches parity.
- Avoid letting the TUI become the only supported operator path.
- Keep the TUI layered cleanly enough that the CLI remains the source of truth.

Subtasks:
- Add tests for any new JSON/reporting contracts the TUI depends on.
- Add Textual-focused tests for:
  - screen composition
  - keyboard handling
  - action dispatch
  - status/error rendering
- Keep a non-interactive path for everything the TUI can launch.
- Keep `homesrvctl tui` as the stable entrypoint; do not introduce `homesrvctl dashboard` as a second public command.
- Remove the old curses renderer only after the Textual path covers the current dashboard and stack actions.
- Document environment assumptions for the TUI, including terminal capabilities and local runtime access.
- Update architecture, file-map, and wiki docs after the migration lands.
  - a separate console script
- Document environment assumptions for the TUI, including terminal capabilities and local runtime access.

## Milestone 5: Release and Distribution Maturity

Status: later

Goal: keep the project easy to ship and easy to consume as the public surface evolves.

### 5.1 Keep release automation healthy

Status: ongoing

Tasks:
- Keep the tagged-release workflow green as packaging and metadata evolve.
- Keep local verification aligned with the release workflow.

Subtasks:
- Periodically verify the release workflow against current GitHub Actions behavior.
- Keep artifact build steps reproducible locally.
- Keep `RELEASING.md` aligned with the actual workflow.

### 5.2 Strengthen packaging polish

Status: planned

Tasks:
- Keep package metadata accurate and public-facing docs aligned with the actual install path.

Subtasks:
- Periodically verify long-description rendering expectations.
- Review whether version strings are defined in too many places.
- Decide whether version sourcing should be centralized further.
- Keep README install guidance aligned with the active release channels.

### 5.3 Decide how much release-note automation is enough

Status: planned

Tasks:
- Decide whether GitHub-generated release notes remain sufficient.
- Avoid adding manual release ceremony unless it improves clarity materially.

Subtasks:
- Review whether notable operator-facing changes need a curated changelog.
- Decide whether to add:
  - `CHANGELOG.md`
  - release-note templates
  - issue labels tied to release notes

## Cross-Cutting Working Rules

These are not standalone deliverables, but they should constrain all future milestones.

### Output and schema discipline

- Watch for output-shape drift in JSON commands as more fields get added.
- Keep schema changes intentional.
- Add regression tests whenever JSON output changes.

### Verification discipline

- Keep the test suite and CI green as the CLI surface grows.
- Keep local verification aligned with GitHub Actions so CI failures are reproducible locally.
- Prefer full local verification before pushing changes that touch shared command surfaces.

### Product discipline

- Keep the operator model simple.
- Prefer idempotent mutation commands.
- Favor small, convergent slices over broad speculative expansion.
