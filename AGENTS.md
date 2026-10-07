# AGENTS

## GUI App Launch

When operating the PySide6 GUI through Codex/Computer Use, launch the helper app from the
repository root with a relative path:

```bash
open dist/Cadmetrics.app
```

If the current working directory is not the repository root, change into the repository root first:

```bash
cd cadmetrics
open dist/Cadmetrics.app
```

The app keeps a native process alive and loads the selected CPython shared library in that process.
Install GUI dependencies and build the app first when needed (macOS with Xcode Command Line Tools):

```bash
uv sync --extra step --extra gui
.venv/bin/python scripts/create_macos_app.py
```

An existing app is not overwritten by default. After closing it, use
`.venv/bin/python scripts/create_macos_app.py --replace` to explicitly rebuild it.
Select the app in Computer Use by its absolute path to avoid similarly named diagnostic apps.
