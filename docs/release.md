# Release Process

cadmetrics uses semantic versioning.

- Patch releases (`v0.2.1`) are for bug fixes and documentation-only release notes.
- Minor releases (`v0.3.0`) are for meaningful feature additions, CSV/API additions, GUI
  workflow improvements, or accuracy/geometry behavior changes.
- Major releases (`v1.0.0`) are for stable public compatibility guarantees or breaking changes
  after the package is mature enough.

The v0.12 release adds `load_elapsed_sec` to `ModelData`, `MeasurementRow`, and CSV output.
Existing `elapsed_sec` now consistently means row calculation time after model preparation;
total uncached time is the sum of both fields. Non-watertight STL volume is now empty rather than
an unreliable mesh-derived value. The GUI also adds cooperative sweep cancellation, a native
Windows GUI launcher, improved component selector sizing, and a centroid visibility control.

v0.12.1 fixes CLI validation of alternate zero-valued sweep specifications and escapes
user-controlled text in Rich error output. It also separates mesh, STEP, and OCP loading
internals, expands mypy coverage to every production module, and upgrades the packaged-GUI smoke
check from an import check to offscreen main-window construction.

Before tagging a release:

1. Update `project.version` in `pyproject.toml`.
2. Run `uv lock`.
3. Run `uv run ruff check .`.
4. Run `uv run mypy`.
5. Run `uv run pytest`.
6. Commit the version bump and changes.
7. Create and push a matching tag, for example:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

Pushing a `v*` tag automatically builds the package and creates a GitHub Release with the
wheel and source distribution attached.

CI also runs a package smoke job on Ubuntu. It builds the wheel, installs the base package,
installs the `step` extra and reads a STEP sample, then installs the `gui` extra and imports the
GUI dependencies. The GUI smoke check constructs and displays the packaged main window with an
offscreen Qt backend and a lightweight viewer substitute, so packaging and widget-composition
failures are detected without depending on a working GPU or VTK rendering context.

During `uv build`, `hatch_build.py` embeds the current git hash into the package as
`cadmetrics._build.GIT_HASH`. This lets installed wheels report `cadmetrics_hash` even though
the wheel does not contain a `.git` directory. If a wheel is built outside a git checkout,
cadmetrics falls back to an embedded hash from the source distribution when one is present, or
`unknown` otherwise.

The release workflow also archives `.hatch-build/cadmetrics-docs-site` as
`cadmetrics-docs-<tag>.zip` and attaches it to the GitHub Release. After extracting the archive,
open `index.html` in a browser to read the documentation offline.
