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

Status: shipped

Goal: make the tool safer to use interactively and easier to reason about when local config gets more complex.

### 2.1 Improve `cloudflared` config safety messaging

Status: shipped

Tasks:
- Add more domain-level diagnostics for unsafe or ambiguous `cloudflared` config states.
- Keep parser errors concrete and remediation-oriented.
- Formalize severity so clearly dangerous semantic states are treated as blocking while lower-confidence risks stay advisory.

Subtasks:
- Detect more cases where one ingress rule unintentionally captures another hostname.
  Current coverage includes broad wildcard rules that may capture traffic intended for a narrower wildcard.
- Improve guidance around wildcard precedence.
  Current warnings now include direct fix hints for reordering or narrowing risky wildcard rules.
- Improve messaging when the config file is valid YAML but semantically unsafe.
- Normalize warning severity in text and JSON output rather than relying only on free-form strings.
- Keep `cloudflared status` healthy for advisory warnings, but fail it for a narrow set of blocking semantic-danger states.
- Treat these states as blocking:
  - duplicate exact hostname entries
  - exact hostname shadowed by an earlier broader rule
  - invalid fallback ordering
- Keep these states advisory unless a stronger concrete conflict is detected:
  - wildcard precedence risk
  - broader wildcard may capture traffic intended for a narrower wildcard

Current baseline:
- `cloudflared status` and `cloudflared config-test` already surface non-fatal ingress warnings for risky wildcard ordering.
- `domain status` and `doctor` already surface the same warnings when they affect hostname troubleshooting.
- `domain status` now also distinguishes missing, duplicate, shadowed, and wrong-target ingress states more explicitly.
- Parser and config-ordering errors already include direct remediation hints for:
  - duplicate ingress entries
  - fallback ordering
  - missing fallback service
  - malformed YAML/list structure

Decision:
- Severity policy uses blocking tiers rather than treating every semantic risk as a hard failure.
- Blocking states should be explicit and narrow so dashboards and routine operator checks do not become noisy.
- Severity should be normalized in command output so the TUI and future automation can consume it predictably.

Completed in this milestone:
- `cloudflared status` and `cloudflared config-test` now normalize ingress issues in text and JSON with explicit blocking versus advisory severity.
- Exact hostname shadowing by an earlier broader rule now fails config health instead of surfacing only as a free-form warning.
- Duplicate exact hostname entries are now treated as blocking semantic config issues even when the YAML is structurally valid.
- Advisory wildcard-precedence risks remain surfaced without flipping healthy runtime status.
- `validate`, `doctor`, `domain status`, and the TUI now consume the same normalized severity model.

### 2.2 Explore safe reload behavior

Status: shipped

Tasks:
- Keep `cloudflared reload` as an explicit operator capability where it is genuinely supported.
- Keep `restart` as the baseline command for mutation flows.

Subtasks:
- Keep `reload` standalone-only rather than auto-using it in domain mutation flows.
- Keep runtime-specific support narrow:
  - allow systemd reload only when `CanReload=yes`
  - keep Docker-managed and process-managed runtimes on restart/manual paths
- Document the operator tradeoff:
  - `reload` is lower-impact when supported
  - `restart` remains the predictable cross-runtime baseline
- Do not introduce hidden runtime-dependent mutation behavior just because reload exists.

Current baseline:
- `cloudflared reload` now exists as a standalone command.
- Systemd-managed `cloudflared` exposes `reload` only when `systemctl show cloudflared --property CanReload --value` reports support.
- Docker-managed and process-managed runtimes currently do not expose reload.
- Domain mutation flows still keep `restart` as the explicit operator path rather than switching to reload automatically.

Decision:
- `cloudflared reload` remains a standalone operator command.
- Domain mutation flows should not auto-reload or auto-prefer reload over restart.
- Runtime behavior should stay explicit rather than clever.

### 2.3 Expand config introspection

Status: shipped

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

Status: shipped

Tasks:
- Preserve a simple operator model where one command does the obvious thing.
- Avoid adding overlapping flags unless they clearly improve safety or automation.
- Keep command naming consistent across lifecycle flows.
- Keep Milestone 2 narrow and policy-focused rather than expanding the command surface.

Subtasks:
- Review new flag proposals against existing domain and deploy verbs.
- Prefer convergent/idempotent mutation behavior on reruns.
- Add regression tests whenever a command gains:
  - a new runtime branch
  - a new output mode
  - a new mutation side effect
- Do not add new flags or subcommands for warning policy unless the normalized severity model proves insufficient.

Decision:
- Milestone 2 should stay narrow:
  - finalize severity policy
  - improve unsafe-config detection and messaging
  - preserve the current command shapes

Completed in this milestone:
- No new warning-policy flags or extra subcommands were added; the existing command surfaces absorbed the severity work.
- Advisory ingress issues now stay advisory in operator-facing reports instead of being flattened into hard failures everywhere.
- Blocking semantic ingress-danger states now fail the relevant health/report commands without changing the deploy or domain mutation verb model.

## Milestone 3: Scaffold and Template Expansion

Status: shipped

Goal: make `app init` more useful without turning `homesrvctl` into a full framework generator.

### 3.1 Mature the existing templates

Status: shipped

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

Completed in this milestone:
- Tightened the generated `node` and `python` READMEs into a consistent structure covering endpoints, runtime inputs, first-run behavior, and health verification.
- Reduced the generated `node` and `python` `.env.example` files to real runtime inputs and clarified that they are optional unless operators need overrides.
- Improved the generated Dockerfile defaults so the Node scaffold installs runtime dependencies during the image build and the Python scaffold sets standard runtime environment flags before installing requirements.
- Kept the generated source baselines small and explicit by adding `/healthz`, returning `405` for unsupported methods, and avoiding extra framework-style scaffolding.
- Added scaffold regression coverage that locks down rendered template manifests plus port and healthcheck consistency across the shipped `node` and `python` templates.

### 3.2 Add a “static app plus API” pattern

Status: shipped

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

Decision:
- The combined static-plus-app pattern is a first-class `app init` template named `static-api`.
- The shipped baseline uses nginx plus a small Python API container behind one hostname.
- The template remains intentionally narrow: basic static assets, a small `/api` service, generated operator guidance, and no frontend build pipeline or framework stack.

Completed in this milestone:
- Added `app init --template static` as the richer static-site app baseline alongside the narrower `site init` scaffold.
- Added `app init --template static-api` as the shipped site-plus-API pattern with a static nginx frontend and a small Python API routed on `/api`.
- Kept the template runtime choice explicit by shipping the first implementation as Python-based rather than introducing multiple runtime variants.
- Added template-specific scaffold and JSON-output regression coverage for the shipped static-site and `static-api` flows.

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

Status: shipped

Tasks:
- Preserve the per-template directory layout under `homesrvctl/templates/app/`.
- Avoid regressing to flat template sprawl.
- Keep template registration and metadata from drifting across command, TUI, docs, and tests.
- Keep scaffold family boundaries explicit between:
  - `site init` templates
  - `app init` templates
- Keep shipped template families covered by parity-style artifact checks and release packaging verification, not only by smoke scaffold tests.

Subtasks:
- Keep template assets grouped under:
  - `placeholder/`
  - `node/`
  - `python/`
  - any future template directories
- Keep scaffold JSON metadata aligned with whatever template structure is shipped.
- Revisit whether template registration should move toward a single source of truth for:
  - valid app template names
  - rendered file lists
  - operator-facing template descriptions
- Keep `app init`, the TUI template picker, and public docs aligned on the same shipped template catalog.
- Audit the current split between `templates/static` and `templates/app/static` and either:
  - document the intentional difference more explicitly
  - or plan a narrow follow-up to reduce duplicated static-site scaffold maintenance
- Add parity-style artifact-coherence coverage for the remaining shipped template families that still lack it:
  - `static`
  - `static-api`
  - `placeholder`
  - `site init`
- Broaden release-oriented packaging verification from Jekyll-only to the rest of the shipped template asset set when that becomes the next maintenance slice.
- Keep template-family conventions explicit for new templates:
  - README presence where operator guidance is required
  - healthcheck expectations where runtime containers are scaffolded
  - whether `.dockerignore` is expected for build-context-based templates
  - rendered-template manifest stability in `--json` output

Current baseline:
- App template names, descriptions, and rendered file manifests now live in `homesrvctl/template_catalog.py`.
- The TUI template picker now reads its shipped app-template choices from the shared scaffold catalog.
- `site init` uses a separate top-level template family from `app init --template static`.
- Artifact-coherence coverage now exists for `site init`, `static`, `static-api`, `placeholder`, `node`, `python`, and `jekyll`.
- Release-packaging verification now checks the full shipped template catalog instead of only Jekyll assets.

Completed in this milestone:
- Added a shared scaffold catalog module so app-template names, operator-facing descriptions, rendered file manifests, and TUI template choices stay aligned.
- Kept the `site init` versus `app init --template static` split explicit in code and docs rather than silently drifting into two overlapping static scaffold families.
- Added parity-style artifact-coherence coverage for the remaining shipped scaffold families: `site init`, `static`, `static-api`, and `placeholder`.
- Broadened release-oriented packaging verification from Jekyll-only coverage to the full shipped template asset set.
- Added a root `.dockerignore` to `static-api` so all build-context-based app templates follow the same packaging convention.

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

Status: shipped

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

Completed in this milestone:
- Added a dedicated Jekyll artifact-coherence test covering compose labels, healthcheck behavior, Dockerfile build flow assumptions, starter `site/` files, and generated README adoption guidance.
- Added `app init --template jekyll` regression coverage for `--profile`, `--docker-network`, and `--traefik-url`.
- Added release-oriented verification that fresh wheel and sdist builds include the full `homesrvctl/templates/app/jekyll` template asset set.
- Expanded generated Jekyll adoption guidance to state which root-level scaffold files operators should keep, which `site/` contents they should replace, how the adopted source root should be laid out, and when native gem dependencies require Dockerfile edits.

## Milestone 4: API Reliability and Cloudflare Coverage

Status: shipped

Goal: decide whether more Cloudflare interactions should move from CLI-assisted flows to API-managed flows.

### 4.1 Audit remaining CLI-dependent Cloudflare flows

Status: shipped

Tasks:
- Review whether any remaining `cloudflared` CLI usage is fragile enough to justify API replacements.
- Keep the current hybrid model unless migration clearly reduces operator risk.

Subtasks:
- Inventory current CLI-dependent operations.
- Separate:
  - runtime/process control concerns
  - Cloudflare control-plane concerns
- Identify which flows are unreliable because of environment assumptions rather than API gaps.

Completed in this milestone:
- Audited the remaining Cloudflare control-plane tunnel-resolution path.
- Kept `cloudflared` CLI usage for local runtime/process concerns, not Cloudflare control-plane tunnel inspection.
- Removed the last `cloudflared tunnel info` fallback from tunnel inspection helpers so unresolved tunnel IDs now require either a local UUID source or account-scoped API context.

### 4.2 Evaluate broader tunnel inspection or management coverage

Status: in progress

Tasks:
- Review whether tunnel inspection should move further to the Cloudflare API.
- Avoid replacing stable local-runtime operations with API calls unless there is a real reliability win.

Subtasks:
- Evaluate whether tunnel target discovery should rely less on local `cloudflared` behavior.
- Evaluate whether tunnel metadata checks should be surfaced in a dedicated command.
- Decide whether tunnel-management work belongs in `homesrvctl` scope at all.

Current baseline:
- `domain` and `validate` now use API-backed tunnel lookup when local UUID sources are unavailable and the local `cloudflared` credentials provide account context.
- `tunnel status` now exists as a dedicated read-only command that reports:
  - configured tunnel reference
  - resolved tunnel UUID
  - resolution source
  - API tunnel status when account-scoped lookup is available
- The remaining tunnel-resolution model is now explicit: local UUID in config first, then account-scoped API lookup when credentials context exists; there is no `cloudflared tunnel info` fallback.

Completed in this milestone:
- Added a first `tunnel status` command instead of burying tunnel inspection only inside `domain` and `validate`.
- Kept the command read-only and diagnostic-focused rather than expanding immediately into tunnel management verbs.
- Classified the remaining `cloudflared` CLI surface as local-runtime or local-config scope:
  - `cloudflared status`
  - `cloudflared restart`
  - `cloudflared reload`
  - `cloudflared logs`
  - `cloudflared config-test`
  - `validate` checks that inspect local ingress config or local runtime state
- Closed the milestone without adding tunnel-management verbs; broader Cloudflare Tunnel management remains out of scope unless a real operator gap appears.

## Milestone 5: Terminal UI (Textual Migration)

Status: shipped

Goal: move `homesrvctl tui` to Textual before the current terminal dashboard grows much larger, while keeping the same CLI entrypoint and the same terminal-first operator model.

Migration policy:
- Textual is the planned long-term TUI implementation.
- The old `curses` dashboard is retired.
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

Status: shipped

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

Status: shipped

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
- Focused `Config` and `Cloudflared` tool items now also have guided tool menus for low-frequency global actions.
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

Completed in this milestone:
- Added guided tool menus for focused `Config` and `Cloudflared` items so global operations are discoverable through the same `Enter` or `o` flow as stack actions.
- Added a guided default-path `config init` flow in the TUI, including overwrite confirmation only when the underlying CLI reports an existing config file that would require `--force`.
- Added a guided `cloudflared logs` flow in the TUI, including a prompt for standard versus `--follow` log-command guidance.
- Kept the launched-command results visible in the focused detail pane so guided flows still resolve to ordinary `homesrvctl` command output.

### 5.5 Make diagnostics explorable

Status: shipped

Tasks:
- Turn the existing rich status output into something easier to inspect interactively.
- Preserve the current operator model where warnings and remediation hints remain explicit.
- Ensure read-heavy commands have an obvious TUI home rather than staying CLI-only.

Subtasks:
 - Add detail views for:
  - `list`
  - `validate`
  - `config show`
  - `tunnel status`
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
  - `tunnel status`
  - per-stack `config show --stack`
  - apex `domain status`
  - cached doctor output
  - `cloudflared status`
  - cached `cloudflared config-test` output
- cached `cloudflared logs` guidance

Completed in this milestone:
- Added cached `cloudflared logs` guidance to the focused `Cloudflared` detail pane so operators can inspect the suggested runtime log command after running the guided flow.
- Kept cached `config init` results visible in the focused `Config` detail pane so global tool actions follow the same inspectable pattern as stack and cloudflared actions.

### 5.6 Retire curses and keep the Textual TUI testable

Status: shipped

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
- The old curses renderer is now removed from the repo.
- The README, architecture notes, and file map now reflect the shipped Textual-only TUI and its terminal/runtime assumptions.

Completed in this milestone:
- Kept the CLI as the source of truth underneath the TUI by routing the shipped Textual flows through existing JSON-backed command surfaces.
- Added TUI regression coverage for the new guided tool-menu paths, cached tool detail rendering, and prompt-driven `config init` / `cloudflared logs` flows.
- Documented the current TUI environment assumptions: interactive terminal I/O plus the same local runtime access that the launched CLI commands require.

## Milestone 6: TUI Mouse Support

Status: complete

Goal: add deliberate mouse support to the Textual TUI without weakening keyboard-first operation or turning the interface into a separate product.

Principles:
- Mouse support should be additive, not a replacement for keyboard navigation.
- Click targets should map to existing TUI concepts rather than introducing a second interaction model.
- Prefer real Textual widgets for clickable surfaces over trying to infer clicks from large text blocks.
- Keep the CLI and JSON command surfaces as the source of truth underneath.

### 6.1 Make the control pane clickable

Status: complete

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

Status: complete

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

Status: complete

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

Status: complete

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

Status: complete

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

Status: complete

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

Status: in progress

Tasks:
- Keep package metadata accurate and public-facing docs aligned with the actual install path.

Subtasks:
- Periodically verify long-description rendering expectations.
- Review whether version strings are defined in too many places.
- Decide whether version sourcing should be centralized further.
- Keep README install guidance aligned with the active release channels.

Current baseline:
- Fresh local `sdist` and wheel builds remain reproducible through `.venv/bin/python -m build`.
- Packaging coverage now asserts that `homesrvctl.__version__` matches `pyproject.toml` so runtime version strings do not drift silently from release metadata.
- Runtime HTTP user-agent strings now derive from the package version instead of hard-coded release literals.

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

## Milestone 8: Scaffold Surface Consolidation

Status: later

Goal: revisit whether the scaffold catalog should grow from the current lightweight app-template registry into a broader unified scaffold registry without changing public command surfaces casually.

### 8.1 Decide whether scaffold registration should unify further

Status: planned

Tasks:
- Evaluate whether `site init` and `app init` should eventually share one broader scaffold registry.
- Keep any registry expansion narrower than a product-surface redesign.

Subtasks:
- Review whether a single registry would materially reduce maintenance beyond the shipped `template_catalog.py` app-template catalog.
- Decide whether site-template metadata should join the same registry shape as app templates.
- Avoid forcing this refactor unless it simplifies tests, docs, and release verification clearly.

### 8.2 Revisit the static-site command split deliberately

Status: planned

Tasks:
- Decide whether the current split between `site init` and `app init --template static` should remain permanent.

## Milestone 9: Full TUI Creation Flows

Status: completed

Goal: make `homesrvctl tui` fully functional for common creation and onboarding work, not only inspection and operations on already-known stacks.

Why this is separate from Milestone 5:
- Milestone 5 was the Textual migration and command-coverage baseline.
- The shipped TUI can already launch several mutations for a focused stack.
- What is still missing is first-class creation flow support when the target stack or domain does not already exist in the current dashboard state.

### 9.1 Add stack-creation entry flows to the TUI

Status: completed

Tasks:
- Make it possible to create a new stack from the TUI without first scaffolding it in the CLI.
- Keep the TUI layered over the existing `site init` and `app init` commands rather than inventing a second creation backend.

Subtasks:
- Add a global creation affordance in the TUI, not tied only to a currently focused existing stack.
- Add a prompt flow for:
  - hostname entry
  - creation mode selection:
    - `site init`
    - `app init`
  - app-template selection for `app init`
  - optional routing/profile inputs that already exist in the CLI:
    - `profile`
    - `docker_network`
    - `traefik_url`
- Keep confirmation and overwrite behavior aligned with the underlying CLI.
- Keep the created stack visible in the dashboard immediately after a successful run.

Current baseline:
- The TUI now exposes a first-class stack-creation flow for hostnames that are not yet present in the dashboard state.
- The flow stays layered over the shipped `site init` and `app init` commands, including optional template and routing override inputs plus overwrite confirmation.

### 9.2 Add domain-onboarding creation flows to the TUI

Status: completed

Tasks:
- Make it possible to onboard a new apex domain from the TUI without dropping back to the CLI.
- Keep the TUI aligned with the existing `domain add` behavior and diagnostics.

Subtasks:
- Add a prompt flow for:
  - apex domain entry
  - optional dry-run choice
  - optional `--restart-cloudflared` choice
- Decide how the TUI should relate domain onboarding to stack context:
  - start from an existing apex stack
  - start from a new hostname/domain entry flow
  - or support both paths explicitly
- Keep post-run DNS/ingress status visible in the detail pane after the mutation completes.
- Reuse the existing `domain status` and `tunnel status` surfaces for follow-up visibility.

Current baseline:
- The TUI now provides a first-class creation-oriented domain entry flow when the operator starts from “I want to onboard a new domain” rather than from an already focused apex stack.
- The flow stays layered over `domain add`, including optional dry-run and restart choices, and reuses the existing `domain status` and `tunnel status` surfaces for follow-up visibility after the mutation completes.

### 9.3 Define the operator model for “fully functional” TUI creation

Status: completed

Tasks:
- Decide which common creation jobs must be possible end-to-end from the TUI before calling it “fully functional”.
- Avoid turning the TUI into a second product surface with divergent semantics.

Subtasks:
- Define the minimum end-to-end flows:
  - create static site stack
  - create app stack from template
  - onboard apex domain
  - inspect resulting routing/domain state
  - run first `up` / verification actions
- Decide which creation inputs remain CLI-only for now, if any.
- Document which flows are intentionally out of scope:
  - bulk/multi-site creation
  - remote creation against another host
  - generalized form-builder style config editing
- Add regression coverage for:
  - prompt validation
  - guided creation dispatch
  - refresh/reselection after creation
  - error rendering when the underlying CLI rejects the requested creation
- Avoid accidental convergence or deprecation without an explicit user-facing decision.

Subtasks:
- Review whether the two static scaffold families still serve distinct operator needs.
- If unification becomes worthwhile, decide whether to:
  - keep both public commands with shared internals
  - deprecate one command surface in a later major slice
  - keep both and document the difference permanently

Decision:
- Treat the TUI as fully functional for common local onboarding once it can create a static site stack, create an app stack from a shipped template, onboard an apex domain, surface resulting routing/domain state, and run first local `up` / verification actions.
- Keep stack scaffold `--dry-run` and explicit `--force` entry CLI-first for now; the TUI may confirm overwrites after a CLI rejection, but it does not need to mirror every scaffold flag as an input control.
- Keep bulk creation, remote-host creation, and generalized config editing out of scope for the TUI.
- Keep `site init` and `app init --template static` as distinct public surfaces for now and document the difference explicitly rather than converging them implicitly.

## Milestone 10: TUI Operator-Facing Polish

Status: planned

Goal: make the Textual TUI read more like an operator dashboard and less like raw internal state by tightening wording, value formatting, and status presentation in the detail panes.

Why this is separate from Milestone 9:
- Milestone 9 made the TUI creation flows operationally complete.
- The remaining gap is not capability but presentation quality.
- The current TUI still exposes several raw boolean-style values and low-level labels that read like implementation details rather than operator-facing UI.

### 10.1 Normalize boolean and status wording in stack and tool detail panes

Status: completed

Tasks:
- Replace machine-flavored boolean text with clearer operator-facing wording where the current display is too raw.
- Keep wording changes narrow and avoid changing the underlying command semantics or JSON shapes.

Subtasks:
- In stack detail:
  - change `compose file: yes/no` to `compose file: exists/does not exist`
  - change `has local config: True/False` to `has local config: yes/no`
- In domain status detail:
  - change `repairable` so it renders:
    - `N/A` when repairability is not relevant because no repair is needed
    - `Yes` when repairable
    - `No` when not repairable
  - change `manual fix required: True/False` to `manual fix required: yes/no`
  - render DNS and ingress record/status sections in bordered table-style layouts instead of loose line lists
  - tighten DNS and ingress field formatting so the operator can scan hostname, match state, target/service, and detail more easily
- Review adjacent detail panes for similar raw `True/False` leakage and group any equivalent wording cleanup into the same polish slice when it stays narrowly presentational.

Current baseline:
- The TUI is functionally complete for common creation/onboarding flows, but several detail-pane fields still render raw booleans or terse yes/no labels that do not read naturally in an operator dashboard.

Completed:
- Stack detail now renders `compose file: exists/does not exist`.
- Effective config detail now renders `has local config: yes/no`.
- Domain detail now renders `repairable` as `N/A`, `Yes`, or `No` depending on overall state.
- Domain detail now renders `manual fix required: yes/no`.
- DNS and ingress sections now render as bordered tables instead of loose line lists.

### 10.2 Define a broader wording pass for user-friendly TUI copy

Status: planned

Tasks:
- Decide which TUI copy patterns should be normalized systematically rather than fixed one field at a time.
- Preserve the current compact dashboard style while making labels and values more human-readable.

Subtasks:
- Review whether these wording patterns should become standard across the TUI:
  - `yes/no`
  - `exists/does not exist`
  - `N/A`
  - title case versus sentence case for labels
- Review whether bordered table-style presentation should become the standard for structured multi-row detail blocks such as:
  - DNS records
  - ingress routes
  - other repeated status rows that currently render as flat text lists
- Identify which fields should remain explicit technical values because operators genuinely need the lower-level wording.
- Add regression coverage for the most visible detail-pane text formatting so future copy cleanups do not drift silently.

## Milestone 11: Cloudflared Config Ownership And Runtime Alignment

Status: completed

Goal: make the `cloudflared` config/setup model portable for public use instead of assuming one host-specific `/etc/cloudflared/config.yml` ownership pattern.

Why this matters:
- Domain lifecycle commands are only safe when `homesrvctl` is updating the same ingress file the active `cloudflared` runtime actually uses.
- A public repo needs an explicit operator model for config ownership, runtime alignment, and privileged setup steps.

### 11.1 Make config ownership explicit

Status: completed

Tasks:
- Change the starter config default for `cloudflared_config` to a shared app-managed path under `/srv/homesrvctl/cloudflared/config.yml`.
- Keep existing installs non-breaking by continuing to honor their explicit configured path.

### 11.2 Add runtime alignment and setup guidance

Status: completed

Tasks:
- Extend `cloudflared status` with setup-alignment reporting:
  - configured path
  - runtime path
  - aligned / misaligned state
  - configured exists / writable
  - whether ingress mutations are safe from the current user
- Add `cloudflared setup` to print exact next-step commands for systemd override repair and config migration.
- Keep systemd as the first-class repair path; keep Docker/process runtimes on a validate-and-report basis.

### 11.3 Prevent partial domain mutations

Status: completed

Tasks:
- Make `domain add`, `domain repair`, and `domain remove` fail before DNS changes when ingress mutation is unsafe.
- Surface setup readiness through `domain status` and the TUI so operators can see mutation availability before running a repair.
- Add a `Fix Setup` path in the TUI `Cloudflared` pane that renders the same setup guidance as the CLI.

### 11.4 Add shared credential access guidance

Status: completed

Tasks:
- Treat the tunnel credentials JSON as secret material that should stay non-public.
- Adopt a first-class shared-group setup model around `root:homesrvctl` for `/srv/homesrvctl/cloudflared`.
- Extend `cloudflared status` and `cloudflared setup` to report credential readability, account-inspection availability, and service user/group context.
- Generate group-based migration commands and a systemd override that sets `Group=homesrvctl`.
- Keep unreadable credentials non-fatal for tunnel health when local tunnel resolution still succeeds, while surfacing setup guidance in the CLI and TUI.

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
