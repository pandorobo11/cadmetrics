# cadmetrics

`cadmetrics` measures CAD models for aerodynamic and drag-area work. Give it an STL or STEP file
and it calculates the model's volume, surface area, base area, and projected area from any
direction, including sweeps over ranges of angles.

You can use it three ways: a desktop GUI, a command-line tool, and a Python library. All three give
the same results.

![cadmetrics GUI showing a satellite STEP sweep](docs/assets/gui-main.png)

## Features

- Reads STL (ASCII and binary) and STEP (`.step`, `.stp`) files
- Calculates volume, surface area, base area (the flat rear faces), and model bounds
- Calculates projected area (the silhouette area) for any direction, counting overlapping parts
  once, together with the silhouette's center
- Sweeps angle of attack / sideslip or roll / pitch ranges
- Treats several files as one model, and lets you include, exclude, or subtract STEP components
- Shows the model and results in an interactive 3D view and chart
- Saves results as CSV, including the settings and cadmetrics version used

## Install

cadmetrics needs Python 3.12 to 3.14.

```bash
pip install "cadmetrics[step,gui]"
```

This installs STEP support and the GUI. If you need less:

| command | what you get |
|---|---|
| `pip install cadmetrics` | CLI and Python API, STL files only |
| `pip install "cadmetrics[step]"` | adds STEP files |
| `pip install "cadmetrics[gui]"` | adds the GUI |
| `pip install "cadmetrics[all]"` | everything, same as `[step,gui]` |

## Quick start

### GUI

```bash
cadmetrics-gui
```

1. Click `Browse` and open a model.
2. Check `Input unit` and `Output unit`.
3. Enter the angles in `Attitude` and click `Run Sweep`.
4. Click a result row to see it in 3D, then click `Save CSV`.

See [Using the GUI](docs/gui.md).

### Command line

```bash
# volume, surface area, and base area
cadmetrics measure model.step

# projected area at 10° angle of attack, in millimeters
cadmetrics project model.step --alpha 10 --output-unit mm

# projected area for alpha 0–90° and beta −10–10° in 5° steps, saved as CSV
cadmetrics sweep model.step --alpha 0:90:5 --beta -10:10:5 --out sweep.csv
```

See [Using the CLI](docs/cli.md).

### Python

```python
from cadmetrics import measure, project, sweep

metrics = measure("model.step")
row = project("model.step", attitude="alpha-beta", alpha_deg=10)
rows = sweep("model.step", attitude="alpha-beta", alpha_deg="0:90:5", beta_deg="-10:10:5")
print(row.projected_area)
```

See [Using Python](docs/api.md).

## Before you start

- cadmetrics uses **X aft, Y right, Z up**. If your model uses other axes, set the axis map.
- STL files have no unit and are read as **meters** by default. Set the input unit to `mm` if
  your STL was exported in millimeters.
- Projected area is calculated from a triangle mesh. The default is tuned for speed; use the
  precise setting for final numbers.

[Key Concepts](docs/concepts.md) explains these in a few minutes.

## Documentation

Guides:

- [Key Concepts](docs/concepts.md): what cadmetrics measures, axes, units, and components
- [Using the GUI](docs/gui.md)
- [Using the CLI](docs/cli.md)
- [Using Python](docs/api.md)

Reference:

- [Attitude Angles](docs/attitude.md)
- [Result Columns](docs/results.md)
- [Accuracy and Mesh Settings](docs/accuracy.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Sample Models](docs/samples.md)

In the GUI, `Help` > `Documentation` opens these pages offline.

## Development

Developer documentation, including the macOS development app, release steps, and internal
design notes, is in the `devdocs/` folder of the source repository.

## License

MIT. See [LICENSE](LICENSE).
