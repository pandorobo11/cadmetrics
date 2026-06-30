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

The app bundle runs the local `.venv/bin/cadmetrics-gui`, so install GUI dependencies first when
needed:

```bash
uv sync --extra step --extra gui
```
