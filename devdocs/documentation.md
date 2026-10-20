# Documentation

cadmetrics keeps two kinds of documentation:

- `README.md` and `docs/`: user documentation. It explains how to use cadmetrics in plain
  language and is bundled into the package as the site opened by the GUI's `Help` >
  `Documentation`.
- `devdocs/`: developer documentation. Internal mechanisms, validation records, build and release
  steps, and other details that users do not need to get their work done.

When a behavior needs both, describe what the user sees and what to do about it in `docs/`, and the
mechanism in `devdocs/`. Pages in `docs/` must not link into `devdocs/`, because `devdocs/` is not
part of the bundled site.

## Writing user docs

- Write for engineers who want to get a measurement done, not for people reading the code.
- Prefer short sentences and everyday words. Explain a technical term the first time it appears.
- Start each page with what the reader can do, then how. Put rarely needed detail last.
- Use the labels exactly as they appear in the GUI and CLI.
- Leave out implementation detail such as library calls, internal tolerances, and validation
  heuristics; put it in `devdocs/` instead.

## Bundled documentation site

`src/cadmetrics/docs_site.py` builds the site with MkDocs. It copies `README.md` as `index.md`,
the whole `docs/` directory, `LICENSE`, and `samples/metadata.json` into a temporary source
directory and builds it with `mkdocs.yml`. Keep the `nav` in `mkdocs.yml` in sync with the files in
`docs/`.

- During `uv build`, `hatch_build.py` builds the site into `.hatch-build/cadmetrics-docs-site` and
  includes it in the wheel as `cadmetrics/_docs_site`.
- When the GUI runs from a checkout, `Help` > `Documentation` rebuilds the site from the checkout
  into a temporary directory, so edits are visible without reinstalling.
- The release workflow also attaches the built site as `cadmetrics-docs-<tag>.zip`.

Preview the site locally with:

```bash
uv run mkdocs build -f mkdocs.yml
```

or open `Help` > `Documentation` in a GUI started from the checkout.

## Images

Images live in `docs/assets/`.

- `gui-main.png`: PySide6 GUI screenshot with the satellite STEP sample loaded, alpha sweep
  configured, the 3D viewer visible, and the results area shown.

When refreshing `gui-main.png`, use a representative STEP sample and keep the left control
panel visible so the README remains useful without additional context.

## Sample models

The `samples/` directory contains deterministic CAD fixtures. Regenerate them with:

```bash
uv run python scripts/generate_samples.py
```

Analytic STEP samples declare millimeter units and are generated at 1000x their meter dimensions,
so the default `--unit auto --output-unit m` reports the same meter-based values as the STL
fixtures. `samples/metadata.json` is the machine-readable list of expected values.
