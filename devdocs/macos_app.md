# macOS Development App

`dist/Cadmetrics.app` is a development helper for running the GUI from a checkout as a normal
macOS app, mainly so accessibility clients such as Computer Use can find it. It is not a
standalone distribution. Users install the GUI with `pip install "cadmetrics[gui]"` and run
`cadmetrics-gui` instead.

## Build and launch

Use a Mac with Xcode Command Line Tools (`xcrun clang`). From the repository root:

```bash
uv sync --extra step --extra gui
.venv/bin/python scripts/create_macos_app.py
open dist/Cadmetrics.app
```

From a development checkout you can also run the GUI directly:

```bash
uv run cadmetrics-gui
```

The generated app is tied to its checkout and Python environment. Its native executable loads
CPython without replacing the process, which retains the macOS app PID used by accessibility
clients such as Computer Use. It runs the ordinary `cadmetrics-gui` entry point; numerical
calculations and the installed CLI are unchanged.

Each launch discovers the Python shared library again. The checkout's executable
`.venv/bin/cadmetrics-gui` selects `.venv/bin/python`; otherwise `uv run python` discovers the
environment and its GUI entry point. Install the GUI extras first: the fallback does not add extras
or change the existing `uv run` synchronization policy. `sys.executable` remains the real selected
interpreter so Python subprocesses and spawn workers use that environment. The uv fallback also
propagates uv's PATH and VIRTUAL_ENV into the GUI process. The launcher sets the
checkout working directory, preserves the previous PATH prefix and inherited display environment,
forwards command-line arguments (except macOS `-psn_` arguments), and returns Python's exit status.

The app stores a relative checkout location in its resources. Moving the checkout together with
its `dist` app preserves that location relationship; it does not make the Python environment
portable. Follow the environment recovery below after moving a checkout. After moving only the
app or checkout, or changing the launcher sources, rebuild the app as well. `--output` and
`--bundle-id` are supported for isolated diagnostic builds. Compilation is
completed in a temporary directory before publishing the bundle. An existing app is refused by
default; close it before explicitly replacing it:

```bash
.venv/bin/python scripts/create_macos_app.py --replace
```

For Computer Use, launch with the relative `open` command above and select the app by its absolute
path. Distinguish startup errors in stderr from app identification or Qt accessibility errors. A
successful process launch alone does not verify the visible GUI. Missing runtime/library/entry
point errors should be resolved by preparing the environment and rebuilding, without changing
macOS security settings.

## Moving a development checkout

Recreate the Python environment at the new location before launching the helper. Normal `uv sync`
installs this project in editable mode, with an absolute source path in a site-packages `.pth` file.
Moving `.venv` preserves that old path and can also leave stale script interpreter paths. Even if
`macos_runtime.py` finds the Python library and executable GUI script, the entry point can fail to
import the product's GUI modules. The existing executable still selects the venv-first route;
runtime discovery does not check product imports and does not trigger uv synchronization on that
route.

Close the app and deactivate any previously activated environment. From the **moved checkout root**,
use a shell without a custom `UV_PROJECT_ENVIRONMENT` override. Preserve the old environment in a
uniquely named backup, then recreate and reinstall the locked STEP/GUI environment:

```bash
previous_env=$(mktemp -d .venv-before-move.XXXXXX)
mv .venv "$previous_env/venv"
uv sync --locked --extra step --extra gui --group dev
.venv/bin/python -I -c 'import cadmetrics; print(cadmetrics.__file__)'
.venv/bin/python -I -c 'from importlib.metadata import distribution; e = next(e for e in distribution("cadmetrics").entry_points if e.name == "cadmetrics-gui"); print(e.load())'
.venv/bin/python scripts/create_macos_app.py --replace
open dist/Cadmetrics.app
```

The first check must print `src/cadmetrics/__init__.py` under the **new** checkout. The second must
load the GUI entry-point function. The rebuild uses the new environment; `--replace` requires the
existing app to be closed. Keep the backup until the new environment works. These commands target
the default `.venv`; creating a portable environment or automatically repairing it at launch is
outside this development helper's scope. See the [Python virtual-environment portability notes](https://docs.python.org/3.12/library/venv.html#how-venvs-work)
and [uv editable-install documentation](https://docs.astral.sh/uv/concepts/projects/sync/#editable-installs).

To reproduce the failure and recovery with the real committed source in a fresh scratch directory:

```bash
.venv/bin/python scripts/verify_editable_move.py --workspace /tmp/cadmetrics-editable-move-check
```

Choose a workspace that does not already exist. The script performs actual locked editable installs,
moves the old checkout out of reach, records successful runtime discovery followed by the actual
GUI script's import failure, and checks the recovered module path and GUI entry-point import.
On macOS it also builds the native helper and checks its pre-recovery import failure. Its report
explicitly distinguishes these checks from real-screen GUI interaction. The native process tests
in `tests/test_macos_launcher.py` use a self-contained probe to check relative bundle location,
PID, argv, spawn, environment and exit status after a move; they do not import the product or prove
that an unchanged editable environment can launch it.

## macOS result selection workaround

Qt 6.11.1 on macOS 27.0.1 can crash in Cocoa's `accessibilitySelectedChildren` when a whole result
row is selected. This was reproduced with the native launcher and with a standalone standard Qt
table, independently of CAD loading or calculations. Keeping a valid native app PID addresses app
identification; the table crash needs its own workaround.

On macOS, the results view keeps one native selected cell and paints the current row with the usual
full-row highlight. Clicking cells or using the arrow keys still chooses the corresponding result,
updates the preview and camera, and saves every result column to CSV. Linux and Windows retain
native whole-row selection. This avoids the observed multi-cell enumeration path while retaining
accessibility; it is not a general fix for Qt accessibility lifetime defects. Other Qt/macOS
combinations still require real-screen validation.
