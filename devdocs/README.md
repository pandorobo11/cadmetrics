# Developer Documentation

These pages are for people working on cadmetrics itself. User documentation lives in
[`README.md`](../README.md) and [`docs/`](../docs/) and is what the GUI shows under `Help` >
`Documentation`; these pages are not part of that site.

- [Requirements](requirements.md): goals, scope, and the intended behavior of each feature
- [Geometry Internals](geometry_internals.md): how STEP/STL values are calculated, boolean-union
  checks, tessellation, and benchmarks
- [Fusion 360 Validation](fusion_validation.md): manual comparison records
- [macOS Development App](macos_app.md): building `dist/Cadmetrics.app`, moving a checkout, and
  macOS-specific workarounds
- [Documentation](documentation.md): how user docs and the bundled site are organized and built
- [Release Process](release.md): versioning, release steps, CI, and compatibility checks

## Development setup

```bash
uv sync --extra step --extra gui
uv run pytest
uv run ruff check .
uv run mypy
```

Run the GUI from the checkout with `uv run cadmetrics-gui`.
