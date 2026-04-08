# Releasing homesrvctl

The published Python distribution name is `homesrvctl`. The CLI command remains `homesrvctl`.

## Source Of Truth

- Package version lives in `pyproject.toml` under `project.version`.
- Release tags must use the form `vX.Y.Z`.
- The pushed tag must exactly match `project.version`.

## Release Channel

- Public releases are published through GitHub Releases.
- Release artifacts are built as:
  - source distribution (`sdist`)
  - wheel
- Tagged releases currently publish to TestPyPI first.
- Production PyPI publishing is intentionally not enabled yet until the TestPyPI path is proven clean.

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
   - publish the built artifacts to TestPyPI through trusted publishing
   - create a GitHub Release and attach the built artifacts
