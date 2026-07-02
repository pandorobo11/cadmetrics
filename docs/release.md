# Release Process

cadmetrics uses semantic versioning.

- Patch releases (`v0.2.1`) are for bug fixes and documentation-only release notes.
- Minor releases (`v0.3.0`) are for meaningful feature additions, CSV/API additions, GUI
  workflow improvements, or accuracy/geometry behavior changes.
- Major releases (`v1.0.0`) are for stable public compatibility guarantees or breaking changes
  after the package is mature enough.

Before tagging a release:

1. Update `project.version` in `pyproject.toml`.
2. Run `uv lock`.
3. Run `uv run ruff check .`.
4. Run `uv run pytest`.
5. Commit the version bump and changes.
6. Create and push a matching tag, for example:

```bash
git tag v0.2.0
git push origin v0.2.0
```

Pushing a `v*` tag automatically builds the package and creates a GitHub Release with the
wheel and source distribution attached.
