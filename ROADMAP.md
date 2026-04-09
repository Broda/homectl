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
  - `cloudflared reload`
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

Status: shipped

Goal: make non-default routing setups and ambiguous domain state easier to understand and safer to operate.

### 1.1 Refresh status and repair diagnostics

Status: shipped

Completed in this milestone:
- `domain status` now distinguishes DNS states more explicitly:
  - missing record
  - wrong type
  - wrong target
  - multiple conflicting records
- `domain status` now distinguishes ingress states more explicitly:
  - exact entry missing
  - duplicate exact entry
  - shadowed entry
  - wrong target
- Repairability messaging is now consistent about what `homesrvctl domain repair` can fix automatically versus when manual cleanup is required first.
- Domain mutation failures now keep non-JSON error output short and actionable for duplicate ingress and conflicting DNS cases.

### 1.2 Formalize the routing-profile model

Status: shipped

Goal: evolve from two standalone override keys into a coherent routing model that can grow without turning the CLI into a pile of flags.

Decision:
- Top-level `docker_network` and `traefik_url` remain the implicit default routing profile.
- Global named profiles live under `profiles`.
- A stack opts into a non-default profile with stack-local `profile`.
- Direct stack-local `docker_network` and `traefik_url` keys remain first-class for one-off exceptions.
- Precedence is:
  - global defaults
  - selected profile values
  - direct stack-local overrides

Completed in this milestone:
- Global config now supports named `profiles`.
- Stack-local `homesrvctl.yml` now supports `profile`.
- `site init` and `app init` support `--profile`.
- Direct stack-local overrides still win over selected profile values.
- The README now documents:
  - the implicit default profile
  - named profile selection
  - one-off direct overrides
  - precedence across all three layers
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

Status: shipped

Completed in this milestone:
- Product-focused routing tests now cover:
  - alternate `docker_network` only
  - alternate `traefik_url` only
  - both overrides together
  - stacks with no override file next to stacks with overrides
  - domain commands against mixed default-versus-overridden stacks
  - JSON output where effective routing data must stay stable

## Milestone 2: Operator UX and Config Safety

Status: next

Goal: make the tool safer to use interactively and easier to reason about when local config gets more complex.

### 2.1 Improve `cloudflared` config safety messaging

Status: in progress

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

Current baseline:
- `cloudflared status` and `cloudflared config-test` already surface non-fatal ingress warnings for risky wildcard ordering.
- `domain status` and `doctor` already surface the same warnings when they affect hostname troubleshooting.
- `domain status` now also distinguishes missing, duplicate, shadowed, and wrong-target ingress states more explicitly.
- Parser and config-ordering errors already include direct remediation hints for:
  - duplicate ingress entries
  - fallback ordering
  - missing fallback service
  - malformed YAML/list structure

### 2.2 Explore safe reload behavior

Status: in progress

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

Current baseline:
- `cloudflared reload` now exists as a standalone command.
- Systemd-managed `cloudflared` exposes `reload` only when `systemctl show cloudflared --property CanReload --value` reports support.
- Docker-managed and process-managed runtimes currently do not expose reload.
- Domain mutation flows still keep `restart` as the explicit operator path rather than switching to reload automatically.

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

Status: mostly shipped

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

Status: mostly shipped

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

### 3.5 Add a narrow Jekyll workflow without expanding the product boundary

Status: shipped

Goal: support an existing Jekyll site as a first-class `app init` template while keeping `homesrvctl` focused on stack-local hosting baselines rather than content-publishing orchestration.

Tasks:
- Add Jekyll only as an `app` template, not as a `site` template.
- Keep the Jekyll source tree inside the stack directory after adoption.
- Keep deploy/runtime flows generic so `up`, `down`, `restart`, `doctor`, and domain commands continue to work unchanged.

Subtasks:
- Add `app init --template jekyll` as the public scaffold surface if this work is implemented.
- Keep the generated stack shape narrow:
  - containerized Jekyll build
  - static serving of the generated site output
  - Traefik labels and healthcheck aligned with existing app templates
- Keep adoption manual in the first slice:
  - scaffold the stack
  - replace starter content with the existing Jekyll site
  - avoid adding an import/copy command in v1
- Avoid new global config fields or new stack-local `homesrvctl.yml` keys in v1.
- Add scaffold and JSON-output regression tests if implemented.

Current baseline:
- `app init --template jekyll` now exists as the public scaffold surface.
- The generated stack uses a stack-local `site/` source tree, a Dockerized Jekyll build, and static serving through nginx behind Traefik.
- The first slice keeps adoption manual: operators replace the generated `site/` contents with their existing Jekyll repo contents and keep the generated stack wiring.

Decision notes:
- This fits the current architecture because deploy commands already operate on any stack with a `docker-compose.yml`.
- Jekyll should be treated as a specific framework exception that remains acceptable only while it stays a small build-plus-host baseline.
- The first slice should not include:
  - git sync
  - CI publishing
  - external repo path management
  - a general build pipeline abstraction

### 3.5.1 Clean up Jekyll template parity and release confidence

Status: in progress

Goal: keep the shipped Jekyll scaffold aligned with the other app templates and safe to release without expanding the product boundary.

Tasks:
- Add parity-focused regression coverage for the shipped Jekyll scaffold.
- Tighten manual-adoption guidance where the current first slice still relies on operator judgment.
- Verify release packaging keeps the Jekyll template assets available in built distributions.

Subtasks:
- Add a dedicated Jekyll artifact-coherence test covering:
  - compose labels and healthcheck behavior
  - Dockerfile build flow assumptions
  - starter `site/` files
  - generated README adoption guidance
- Add `app init --template jekyll` regression coverage for:
  - `--profile`
  - `--docker-network`
  - `--traefik-url`
- Add a release-oriented verification step or test that built artifacts include:
  - `homesrvctl/templates/app/jekyll`
  - all rendered Jekyll template files
- Expand Jekyll adoption guidance for:
  - which generated stack files operators should keep
  - which `site/` contents operators should replace
  - when native gem dependencies require Dockerfile edits
  - the expectation that the adopted Jekyll source root lives directly under `site/`
- Revisit `.dockerignore` coverage only if real adoption shows missing common Jekyll cache or bundle paths.

Current baseline:
- The Jekyll scaffold already has dedicated scaffold and JSON-output regression tests.
- The generated scaffold README already documents:
  - keeping the generated stack wiring files
  - replacing the `site/` contents with the adopted Jekyll source tree
  - extending the Dockerfile when native gem dependencies require more packages
- Remaining follow-up is mainly:
  - parity-style coherence coverage
  - routing-override coverage
  - built-distribution verification

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

Status: shipped

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
- Textual is now added as a dependency for the TUI migration.
- The current implementation shells out to existing `--json` commands for:
  - `list`
  - `cloudflared status`
  - `validate`
  - `config show`
  - stack-focused `config show --stack`
  - apex `domain status`

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
- The Textual dashboard now covers that baseline and extends it with:
  - per-stack effective config detail
  - apex-domain status detail
  - cached last-action detail for stack and cloudflared actions

### 5.3 Improve layout and theming with Textual

Status: shipped

Tasks:
- Use Textual to move beyond the compact curses layout and give the TUI a clearer long-term visual structure.
- Keep the interface intentionally roomy and warm rather than dense and utilitarian.

Subtasks:
- Define a stable Textual layout with:
  - a full-width summary strip across the top
  - a left control pane below it
  - a right detail pane below it
  - a persistent command/status bar across the bottom
- Keep the summary strip informational only rather than making summary cards the primary navigation surface.
- Use a unified vertical cursor in the left control pane.
- Group a small `Tools` section above the larger `Stacks` section in that pane.
- Make the right detail pane operational:
  - show the focused item
  - show the current state
  - show the relevant actions or action guidance
- Use warm summary cards for:
  - stacks
  - `cloudflared`
  - validation
- Define visual states for:
  - selected
  - success
  - warning
  - error
  - running/busy
- Replace the old split navigation model:
  - no section-by-section summary navigation
  - no separate `a`/`d` stack mode
  - `w`/`s` and arrow keys should drive the primary vertical movement
- Keep the theme intentional and readable on typical terminal backgrounds without introducing a second “brand system” separate from the CLI.

Current baseline:
- The Textual dashboard now uses a roomy warm-console layout.
- The top summary strip now has three informational cards for:
  - stacks
  - `cloudflared`
  - validation
- The left pane is now the primary navigation/control surface with:
  - `Tools`
  - `Stacks`
- The left pane now uses a unified vertical cursor instead of separate section and stack selection models.
- The right pane now follows the focused control item and shows operational detail for:
  - global tools
  - focused stacks
- The bottom bar now stays visible as a persistent command/status bar.

### 5.4 Add guided flows for common operations

Status: in progress

Tasks:
- Make the common multi-step operations easier to run without memorizing command sequences.
- Keep the Textual app aligned with the existing CLI verbs and mutation behavior.
- Expand the TUI until the public CLI surface is covered by either:
  - a guided mutation flow
  - an explorable read-only view
  - an action launcher with visible results

Subtasks:
- Define the guided-path structure explicitly instead of growing ad hoc prompts:
  - a focused stack action menu for stack-local and apex-domain operations
  - focused tool menus for global operations such as config and cloudflared
  - confirmation prompts for destructive or high-impact mutations
  - follow-up result views that keep the launched command output visible
- Add guided flows for stack-focused commands:
  - `site init`
  - `app init`
  - `up`
  - `down`
  - `restart`
  - `doctor`
- Add guided flows for apex-domain commands:
  - `domain add`
  - `domain repair`
  - `domain remove`
- Add guided flows for global-tool commands where a prompt is useful:
  - `config init`
  - `cloudflared restart`
  - `cloudflared reload`
  - `cloudflared logs`
- Decide how Textual prompts/screens should handle shared inputs:
  - hostname selection from the focused stack
  - template selection
  - profile selection
  - routing overrides
  - restart/reload choices
  - destructive-action confirmation
- Break guided-path work into implementation slices so coverage can land incrementally:
  - introduce the stack action menu
  - route existing direct stack actions through that menu without removing hotkeys
  - add apex-only domain actions to the same menu
  - add global tool menus
  - add richer follow-up prompts only where the simple launcher stops being sufficient
- Track command coverage explicitly so the TUI roadmap does not stop at the current dashboard:
  - `config init`
  - `config show`
  - `domain add`
  - `domain status`
  - `domain repair`
  - `domain remove`
  - `site init`
  - `app init`
  - `up`
  - `down`
  - `restart`
  - `list`
  - `cloudflared status`
  - `cloudflared config-test`
  - `cloudflared logs`
  - `cloudflared restart`
  - `cloudflared reload`
  - `validate`
  - `doctor`
- For each public CLI command, decide which TUI shape it belongs to:
  - guided flow
  - read-only detail view
  - direct action from the dashboard
- Keep all TUI-driven mutations understandable as ordinary `homesrvctl` operations underneath.

Current baseline:
- The Textual TUI now includes a first guided scaffold flow for `app init`, using a minimal template picker that still shells out to the existing CLI command underneath.
- Apex-focused stacks now also support guided confirmation prompts for `domain add` and `domain remove`.
- Focused stacks now also have a guided stack action menu so the existing stack and apex-domain actions are discoverable without relying only on hotkeys.
- Focused stacks can already launch:
  - `site init`
  - `app init`
  - `up`
  - `down`
  - `restart`
  - `doctor`
  - `domain add`
  - `domain repair`
  - `domain remove`
- Remaining guided-flow gaps are mostly around global tools such as:
  - `config init`
  - `cloudflared logs`
  - richer prompt coverage for shared inputs beyond the current template picker and confirmations

### 5.5 Make diagnostics explorable

Status: in progress

Tasks:
- Turn the existing rich status output into something easier to inspect interactively.
- Preserve the current operator model where warnings and remediation hints remain explicit.
- Ensure read-heavy commands have an obvious TUI home rather than staying CLI-only.

Subtasks:
 - Add detail views for:
  - `list`
  - `validate`
  - `config show`
  - `domain status`
  - doctor output
  - `cloudflared` status
  - `cloudflared config-test`
  - `cloudflared logs`
 - Surface routing context clearly:
  - default target
  - effective target
  - profile
  - override source
 - Surface remediation hints directly for:
  - ingress warnings
  - domain repairability
  - config problems

Current baseline:
- The Textual TUI already exposes explorable detail views for:
  - `list`
  - `validate`
  - `config show`
  - per-stack `config show --stack`
  - apex `domain status`
  - cached doctor output
  - `cloudflared status`
  - cached `cloudflared config-test` output
- The main remaining read-heavy gap in this milestone is `cloudflared logs`.

### 5.6 Retire curses and keep the Textual TUI testable

Status: in progress

Tasks:
- Remove the transitional curses implementation after the Textual dashboard reaches parity.
- Avoid letting the TUI become the only supported operator path.
- Keep the TUI layered cleanly enough that the CLI remains the source of truth.
- Verify that each supported public command has either TUI coverage or an explicit out-of-scope reason recorded in this milestone before calling the migration done.

Subtasks:
- Add tests for any new JSON/reporting contracts the TUI depends on.
- Add Textual-focused tests for:
  - screen composition
  - keyboard handling
  - action dispatch
  - status/error rendering
- Add coverage reviews for command parity so new CLI commands do not quietly ship without a TUI decision.
- Keep a non-interactive path for everything the TUI can launch.
- Keep `homesrvctl tui` as the stable entrypoint; do not introduce `homesrvctl dashboard` as a second public command.
- Remove the old curses renderer only after the Textual path covers the current dashboard, stack actions, and the intended command-coverage baseline above.
- Document environment assumptions for the TUI, including terminal capabilities and local runtime access.
- Update architecture, file-map, and wiki docs after the migration lands.
  - a separate console script
- Document environment assumptions for the TUI, including terminal capabilities and local runtime access.

Current baseline:
- The Textual TUI already has focused tests for:
  - snapshot/data loading
  - prompt rendering
  - keyboard-driven action dispatch
  - status and detail rendering
- The legacy curses renderer is still present, so this milestone remains open until retirement and final parity review are complete.

## Milestone 6: TUI Mouse Support

Status: planned

Goal: add deliberate mouse support to the Textual TUI without weakening keyboard-first operation or turning the interface into a separate product.

Principles:
- Mouse support should be additive, not a replacement for keyboard navigation.
- Click targets should map to existing TUI concepts rather than introducing a second interaction model.
- Prefer real Textual widgets for clickable surfaces over trying to infer clicks from large text blocks.
- Keep the CLI and JSON command surfaces as the source of truth underneath.

### 6.1 Make the control pane clickable

Status: planned

Tasks:
- Replace the plain-text left control pane with clickable Textual widgets.
- Keep the current visual grouping of `Tools` above `Stacks`.
- Keep keyboard focus and mouse focus aligned to the same selected item.
- Give selected rows a visually unambiguous highlight — not just a `>` prefix.
- Show compose status as a compact colored symbol rather than verbose `[compose=yes]` / `[compose=no]` text.

Subtasks:
- Introduce reusable row widgets for:
  - tool items
  - stack items
- Preserve the current selected-state styling for the active row.
  Current baseline: selected item is indicated by a `>` prefix in plain text — replace this with a highlight background or bold colored text so the selection is immediately obvious.
- Stack rows should display compose status as a colored symbol:
  - `●` in the teal accent color when a compose file is present
  - `○` in dim/muted color when no compose file exists
  This replaces the current `[compose=yes]` / `[compose=no]` notation and frees ~14 characters per row.
- Section headers ("Tools", "Stacks") should be styled as non-clickable label widgets with the accent color, clearly visually distinct from the clickable item rows below them.
- Define three explicit CSS states for control row widgets:
  - normal (default)
  - `--selected` (highlighted — drives both keyboard and mouse focus)
  - hover (subtle tint for mouse affordance)
- Keep keyboard focus and click focus on the same selected widget — the internal `selected_control_index` state should drive which widget receives the `--selected` class.
- Support click-to-focus for:
  - `Config`
  - `Cloudflared`
  - `Validate`
  - stack rows
- Ensure clicking a row updates the right detail pane exactly as keyboard movement does.
- Add tests for:
  - clicking a tool row
  - clicking a stack row
  - selection-state rendering after a click

### 6.2 Make modal prompts clickable

Status: planned

Tasks:
- Convert guided prompt screens from text-only option lists into clickable option rows or buttons.
- Preserve full keyboard support for every prompt.
- Keep the visual style of modal option rows consistent with the control pane row widgets.

Subtasks:
- Make the app-template picker clickable.
- Make the stack action menu clickable.
- Make confirmation prompts clickable.
  Current baseline: `ConfirmActionScreen` shows plain `Static` text. Replace with real `Button` widgets for "Confirm" and "Cancel" using the existing palette — the confirm/cancel text body stays as a `Static` above them.
- When converting option lists to widgets, each option row should:
  - Show the number shortcut as a styled dim badge (1–9 still fires immediately via `on_key`)
  - Show the option label prominently
  - Show the description in muted text below or inline
  Current baseline: options are rendered as `> 1. label\n  description` string lines — the `>` prefix is the only selection indicator.
- Use the same `--selected` CSS class and styling for selected modal rows as for control pane rows — one consistent selection visual, not a second design system.
- Review modal container widths in CSS (`#app_init_prompt` at 72, `#confirm_prompt` at 64, `#stack_action_prompt` at 72) and adjust if widget rows with padding require more space than tight string columns.
- Ensure clicking an option triggers the same underlying callback path as pressing Enter.
- Add tests for:
  - clicking a template option
  - clicking a stack action option
  - clicking confirm versus cancel

### 6.3 Add clickable action surfaces in the detail pane

Status: planned

Tasks:
- Let the focused detail pane expose clickable actions for the current item instead of relying only on hotkeys and menu prompts.
- Keep the action set consistent with the currently focused tool or stack.
- Structure the detail pane as two zones: a scrollable content area and a fixed action button strip.

Subtasks:
- Restructure the detail pane layout into two zones:
  - A scrollable content area at the top (hostname/tool info, config, domain status, last action result).
    Current baseline: `#detail_box` is a plain `Static` inside a `Vertical` with no scroll — long output (many DNS records, many checks, long file lists) overflows silently. Replace with a `VerticalScroll` or `ScrollableContainer`.
  - A fixed action button strip at the bottom, always visible.
- The action button strip should show only the 3–5 highest-value actions for the current focus:
  - Stacks: `Up`, `Down`, `Restart`, `Doctor`, `Actions Menu`
  - Cloudflared: `Config Test`, `Reload`, `Restart`
  - Config / Validate: `Refresh`
  Destructive or lower-frequency operations (domain add/remove) remain in the guided action menu, not as persistent buttons.
- When the action button strip is present, simplify the command bar to global-only keys (`w/s navigate · r refresh · q quit`).
  Current baseline: the command bar for stack focus dumps 12+ bindings in a single line. Once actions are visible in the pane, contextual keys no longer need to live in the bar.
- Button labels should be 1–2 words. Define button states in CSS using the existing palette:
  - normal: teal border
  - focused/hover: amber border or teal background
  - active/pressed: inverted
- Action buttons should dispatch through the same `action_*` methods that keyboard bindings already use — no new command paths.
- Add apex-only detail actions (within the action menu flow, not as persistent buttons):
  - `domain add`
  - `domain repair`
  - `domain remove`
- Add detail actions for focused tools where appropriate:
  - `cloudflared config-test`
  - `cloudflared reload`
  - `cloudflared restart`
- Ensure detail actions launch the same prompt or command path as the keyboard bindings.
- Add tests for clicking detail actions and verifying the expected command path runs.

### 6.4 Decide whether summary cards should be clickable

Status: planned

Tasks:
- Decide whether the top summary strip should remain informational only or support click-to-focus behavior.
- Avoid adding clicks there unless they improve navigation rather than duplicating the control pane needlessly.
- Fix the current card styling gap when converting to widgets.

Decision guidance:
- Make cards clickable to focus the related tool in the control pane.
  Clicking the Stacks card focuses the first stack item. Clicking Cloudflared focuses the Cloudflared tool row. Clicking Validate focuses the Validate tool row.
  This is shallow, predictable, and adds discoverability without ambiguity.
- Keep cards informational-only in the keyboard flow — `w/s` still drives the control pane exclusively. The click is additive.

Subtasks:
- Evaluate whether clicking a summary card should:
  - focus the related tool (recommended — see above)
  - open a related menu
  - remain disabled by design
- When converting cards to widgets, fix the current styling:
  Current baseline: `_summary_card()` emits `f"{title}\n\n{detail}"` — the title is unstyled plain text, indistinguishable from the detail text.
  - Render the card title in the accent color (`#ffcf5a` bold).
  - Add a single-line status indicator as the first line of the card body, before secondary detail text:
    - Stacks card: `✓ 3 ready` / `○ none ready` / `✗ error`
    - Cloudflared card: `✓ active` / `⚠ 2 warnings` / `✗ inactive`
    - Validate card: `✓ all passing` / `✗ 2 failing`
  The status symbol line makes health state readable at a glance without reading full sentences.
- If click-to-focus is enabled, add click handling for:
  - stacks summary
  - cloudflared summary
  - validate summary
- Keep the interaction shallow and predictable.
- Document the decision either way in the TUI docs.

### 6.6 Integrate visual polish during widget migration

Status: planned

Goal: apply visual improvements that are not directly about clickability but belong in the same implementation pass as the widget migration. Patching the string-rendering layer before M6 would create throwaway work — these changes should land together with 6.1–6.4.

Tasks:
- Add status-based color to rendered detail text using Rich markup.
- Apply Rich markup to section headers in detail view render helpers.
- Make the right pane title dynamic and contextual.
- Collapse multi-line help text blocks to compact single-line hints.
- Simplify the command bar to global-only keys once contextual actions live in the detail pane.
- Add a CSS palette reference for status color states.

Subtasks:
- Update `render_stack_action_detail()` in `data.py`:
  - Wrap status `"ok"` in green markup, `"failed"` in red.
  - Wrap `PASS` check markers in green, `FAIL` in red.
- Update `render_tool_action_detail()` in `data.py`: same color pattern for `"ok"` / `"failed"` status values.
- Update `render_domain_status_detail()` in `data.py`:
  - Color domain overall status: `"ok"` green, `"partial"` yellow, `"misconfigured"` red.
  - Color individual DNS record status values per entry.
- Update `_cloudflared_detail_text()` in `app.py`:
  - Color `active` green, `inactive` yellow.
  - Color `config ok: True` green, `config ok: False` red.
- Apply accent color markup to section headers in all four render helpers in `data.py`:
  - "Effective config", "Domain status", "Last action", "Cloudflared Detail", "Config Detail", "Validate Detail"
  Currently these are plain strings at the same visual weight as data rows.
- Replace the static `"Detail"` pane title with a dynamic title reflecting the focused item:
  - `Stack: example.com`
  - `Tool: Cloudflared`
  - `Tool: Validate`
  - `Tool: Config`
  Update this title in `_render()` alongside other widget updates.
- Replace the multi-line help text at the bottom of each detail view with a single compact hint line.
  Current baseline: `_stack_detail_text()` ends with 7 lines of prose describing available key bindings.
  Replace with one short line, e.g. `· enter menu  · u up  · x down  · r refresh`.
  This hint line can be removed entirely once action buttons from 6.3 are visible in the pane.
- Add a CSS comment block near the top of the `CSS` string in `app.py` documenting the intended palette use for status states:
  - status ok / success: green
  - status warning: yellow / amber
  - status error / failed: red
  - accent / titles: `#ffcf5a`
  - primary borders / highlights: `#1fd6c1` / `#13bfae`
- Verify all Rich markup renders correctly in Textual `Static` widgets (no visible escape sequences).

### 6.5 Keep mouse support testable and accessible

Status: planned

Tasks:
- Add proper Textual interaction coverage for mouse-driven behavior.
- Keep mouse affordances readable in terminals that vary widely in color and capability.

Subtasks:
- Add Textual pilot tests for:
  - click selection
  - click-driven prompt confirmation
  - click-driven action dispatch
  - mixed keyboard-plus-mouse interaction sequences
- Verify that hover, focus, and selected states stay visually distinct.
- Ensure mouse support does not break operation in terminals where mouse reporting is unavailable or disabled.
- Document mouse behavior and terminal assumptions in the README and wiki when this milestone lands.

## Milestone 7: Release and Distribution Maturity

Status: later

Goal: keep the project easy to ship and easy to consume as the public surface evolves.

### 7.1 Keep release automation healthy

Status: ongoing

Tasks:
- Keep the tagged-release workflow green as packaging and metadata evolve.
- Keep local verification aligned with the release workflow.

Subtasks:
- Periodically verify the release workflow against current GitHub Actions behavior.
- Keep artifact build steps reproducible locally.
- Keep `RELEASING.md` aligned with the actual workflow.

### 7.2 Strengthen packaging polish

Status: planned

Tasks:
- Keep package metadata accurate and public-facing docs aligned with the actual install path.

Subtasks:
- Periodically verify long-description rendering expectations.
- Review whether version strings are defined in too many places.
- Decide whether version sourcing should be centralized further.
- Keep README install guidance aligned with the active release channels.

### 7.3 Decide how much release-note automation is enough

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
