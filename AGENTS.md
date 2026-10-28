# AGENTS

Run commands from the repository root. In a worktree or a checkout with another directory name,
change into it with:

```bash
cd "$(git rev-parse --show-toplevel)"
```

Developer documentation is in [`devdocs/`](devdocs/README.md); user documentation is in
[`README.md`](README.md) and [`docs/`](docs/).

## Checks

Install dependencies, then run the same checks as CI before committing:

```bash
uv sync --extra step --extra gui
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

## GUI App Launch

When operating the PySide6 GUI through an accessibility client such as Computer Use, build and
launch the helper app (macOS with Xcode Command Line Tools):

```bash
.venv/bin/python scripts/create_macos_app.py
open dist/Cadmetrics.app
```

`dist/` is ignored by git, so each checkout or worktree builds its own app. The app keeps a native
process alive and loads the selected CPython shared library in that process.

An existing app is not overwritten by default. After closing it, use
`.venv/bin/python scripts/create_macos_app.py --replace` to explicitly rebuild it.
Select the app in Computer Use by its absolute path to avoid similarly named diagnostic apps.
See [`devdocs/macos_app.md`](devdocs/macos_app.md) for details and troubleshooting.
