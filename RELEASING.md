# Releasing homectl

The published Python distribution name is `homesrvctl`. The CLI command remains `homectl`.

## Source Of Truth

- Package version lives in `pyproject.toml` under `project.version`.
- Release tags must use the form `vX.Y.Z`.
- The pushed tag must exactly match `project.version`.

## Release Channel

- Public releases are published through GitHub Releases.
- Release artifacts are built as:
  - source distribution (`sdist`)
  - wheel
- PyPI publishing is intentionally not enabled yet.

## Release Notes

- GitHub Releases are created with GitHub-generated notes.
- Release notes are therefore derived from the changes included since the previous release.

## Release Steps

1. Update `project.version` in `pyproject.toml`.
2. Commit the version bump.
3. Create and push the matching tag, for example `v0.1.0`.
4. GitHub Actions will:
   - run the shared Python checks workflow
   - verify the tag matches `project.version`
   - build `sdist` and `wheel`
   - create a GitHub Release and attach the built artifacts
