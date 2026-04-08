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

Status: planned

Tasks:
- Add product-level support for more than one local ingress URL.
- Ensure domain lifecycle commands resolve the correct ingress target from the effective routing config.
- Ensure doctor and validation flows report the effective routing target clearly.

Subtasks:
- Decide whether additional ingress targets belong in:
  - named routing profiles
  - direct stack-local overrides only
- Extend domain-status output so it clearly shows:
  - default target
  - effective target
  - why the effective target differs
- Add tests for mixed setups where:
  - one stack uses the default ingress
  - another stack uses an alternate ingress

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

Status: in progress

Tasks:
- Improve visibility into effective config resolution.
- Make it easier to understand what global config plus stack-local config combine into.

Subtasks:
- Extend `config show --json` if more effective-config detail becomes necessary.
- Extend stack-focused config inspection beyond `config show --stack example.com` if operators need deeper routing visibility.
- Decide whether effective config inspection belongs under:
  - `config`
  - `doctor`
  - `domain status`
- Ensure any new output clearly separates:
  - global values
  - inherited defaults
  - stack-local overrides

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
- Review whether `.env.example` files explain only what users actually need.
- Review whether Dockerfiles use reasonable defaults without too much magic.
- Review whether generated source files include only the minimum useful comments.

### 3.2 Add a “static app plus API” pattern

Status: planned

Goal: support a common self-hosted pattern where one hostname serves static assets and proxies to a small app service.

Tasks:
- Define the scope of a combined static-plus-app scaffold.
- Decide whether it should be a first-class app template.

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

### 3.3 Decide the philosophy boundary for scaffolds

Status: planned

Tasks:
- Decide how opinionated `homesrvctl` should be about application bootstrapping.
- Keep the project focused on hosting operations, not full app generation.

Subtasks:
- Write down what belongs in a scaffold:
  - Compose
  - Dockerfile
  - minimal app entrypoint
  - docs
- Write down what does not belong by default:
  - large framework setups
  - heavy frontend stacks
  - production app architecture choices
- Use that boundary to guide future template additions.

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
