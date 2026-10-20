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

v0.12.2 corrects STEP unit handling and preserves loose or surface-only geometry in single- and
multi-file inputs. It rejects inconsistent STL shell winding instead of reporting unreliable
volume, protects input CAD files from CSV export overwrites in the CLI and GUI, and avoids leaking
XCAF documents while reading component names.

v0.13.0 hardens GUI background-operation teardown to prevent native crashes and keeps controller
state changes on the GUI thread. It validates attitude, sweep, and model-loading options before
file I/O; splits STEP finalization into explicit processing stages; replaces the materialized
results widget with a scalable table model; and makes one typed result schema drive CSV, GUI, and
documentation fields. GUI packaging and interaction checks now exercise behavior instead of
matching implementation source text.

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

The CI package job uploads the built distributions as a run-scoped artifact. A separate clean
install job downloads that exact artifact, installs the wheel with both `step` and `gui` extras in
a fresh Python environment outside the checkout, and exercises the installed CLI, STEP support,
packaged documentation, and GUI. This keeps package validation tied to the artifact that was
actually built instead of rebuilding it in a later job.

During `uv build`, `hatch_build.py` embeds the current git hash into the package as
`cadmetrics._build.GIT_HASH`. This lets installed wheels report `cadmetrics_hash` even though
the wheel does not contain a `.git` directory. If a wheel is built outside a git checkout,
cadmetrics falls back to an embedded hash from the source distribution when one is present, or
`unknown` otherwise.

The release workflow also archives `.hatch-build/cadmetrics-docs-site` as
`cadmetrics-docs-<tag>.zip` and attaches it to the GitHub Release. After extracting the archive,
open `index.html` in a browser to read the documentation offline.

## Python compatibility

The package targets Python 3.12, 3.13, and 3.14 (`>=3.12,<3.15`). The development
interpreter in `.python-version` remains 3.12, as do the minimum syntax targets
for Ruff and mypy. CI explicitly selects each matrix interpreter for both sync
and execution; it tests all three versions on Linux, macOS, and Windows.
The clean-install job additionally checks wheel and sdist installs on all three
Python versions on Linux. These jobs must pass before merging compatibility changes.

When widening the range, retain existing dependency versions where possible,
regenerate `uv.lock`, and run `uv sync --locked --python VERSION --extra step
--extra gui --group dev` in isolated environments. Verify the full test suite,
lint, types, clean distribution installs, and native macOS launcher tests.
The launcher test fixture must allow the same Python range as the package.
The packaged GUI smoke uses a substitute viewer; separately exercise real VTK
rendering, camera movement, zoom, component filtering, and image export, and
compare representative STEP/STL measurements and attitude sweeps across Python
versions. Local macOS success does not establish Windows or Linux runtime support.

Local compatibility validation on 2026-10-18 (macOS 27.0.1, Apple Silicon):

- CPython 3.12.12, 3.13.5, and 3.14.7 each passed all 340 tests, Ruff lint and
  formatting checks, and mypy. The tests include native launcher process checks.
- Lock regeneration retained every dependency version, including cadquery-ocp
  7.9.3.1.1, PySide6 6.11.1, and VTK 9.6.2.
- Each version passed real Qt/VTK viewer rendering, camera changes, zoom,
  screenshot capture, component filtering, and viewer shutdown.
- Unit-cube STEP, 1x2x3-box binary STL, cylinder STEP, and two-box STEP produced
  exactly matching volume, surface area, projected area (alpha=15, beta=10),
  and six-point sweeps (alpha=0,15,30; beta=0,10) across the three interpreters.
- Wheel and sdist clean installs passed CLI help, STEP inspection, and packaged
  GUI/documentation smoke on all three versions. These installs resolved
  dependencies independently from the development lock.

After updating to main f6591c6, all three interpreters passed 340 tests, Ruff,
and mypy. A Python 3.14 app bundle launched through Launch Services, loaded and
rendered unit-cube STEP, and completed a one-row sweep through the native UI.
The four-model numerical/rendering comparison and all six wheel/sdist install
checks were also repeated successfully after this main update. Windows/Linux
results are tracked in the compatibility pull request CI.
