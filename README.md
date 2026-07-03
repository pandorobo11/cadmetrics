# cadmetrics

`cadmetrics` calculates volume, surface area, and projected area for STL and STEP files.
It provides a CLI, Python API, and PySide6 desktop GUI for aerodynamic projected-area and
drag-area checks.

## Features

- Read STL ASCII/Binary and STEP (`.step`, `.stp`)
- Calculate volume and surface area
- Calculate orthographic projected outline area with overlapping projected regions removed
- Sweep alpha/beta or roll/pitch angle ranges
- Report equivalent alpha/beta, roll/pitch, and unit-vector direction values
- Report projected-area centroids in 2D projection coordinates and 3D model coordinates
- Report model XYZ coordinate bounds in the selected output unit
- Report the cadmetrics package version and git hash used for each calculation
- Export CSV from CLI and GUI
- Inspect geometry in a local PySide6/PyVista GUI
- Toggle STEP solid components in the GUI advanced settings

## GUI Preview

![cadmetrics GUI showing a satellite STEP sweep](docs/assets/gui-main.png)

## Install

STL-only usage:

```bash
pip install cadmetrics
```

STEP support:

```bash
pip install "cadmetrics[step]"
```

PySide6 GUI:

```bash
pip install "cadmetrics[gui]"
```

STEP support and GUI together:

```bash
pip install "cadmetrics[step,gui]"
```

From a local checkout with `uv`:

```bash
uv sync --extra step --extra gui
```

cadmetrics currently targets Python 3.12.

## Quickstart

The STEP examples below require `cadmetrics[step]`.

Measure a STEP file:

```bash
cadmetrics measure samples/unit_cube/unit_cube.step
```

Calculate projected area from angle of attack and sideslip:

```bash
cadmetrics project samples/satellite/satellite.step \
  --output-unit mm \
  --attitude alpha-beta \
  --alpha 60 \
  --beta 0
```

Calculate projected area from roll and pitch:

```bash
cadmetrics project samples/satellite/satellite.step \
  --output-unit mm \
  --attitude roll-pitch \
  --roll 0 \
  --pitch 60
```

Calculate projected area from an explicit direction vector:

```bash
cadmetrics project samples/satellite/satellite.step \
  --output-unit mm \
  --attitude vector \
  --direction 0.5,0,0.8660254
```

Sweep every combination of attitude ranges and write CSV:

```bash
cadmetrics sweep samples/satellite/satellite.step \
  --output-unit mm \
  --attitude alpha-beta \
  --alpha 0:90:5 \
  --beta -10:10:5 \
  --out sweep.csv
```

Launch the desktop GUI:

```bash
cadmetrics-gui
```

## Coordinate and Attitude Convention

The default coordinate convention is:

```text
X aft, Y right, Z up
```

`alpha`, `beta`, `roll`, and `pitch` describe the projection direction attitude, not the
model rotation.

If the source model axes do not match this convention, remap them before calculation:

```bash
cadmetrics project model.step --axis-map x,-z,y --alpha 10
```

`--axis-map` lists the source axes used as cadmetrics `X,Y,Z`.

Use `--direction x,y,z` when you want the least ambiguous input.

See [Attitude Definition](docs/attitude.md) for formulas and examples.

## Units

`--unit` describes the input model length unit. Its default is `auto`:

- STEP units are read from the file
- STL is assumed to be meters

`--output-unit` controls reported coordinates, areas, and volumes. Supported explicit units are
`m`, `mm`, `cm`, `in`, and `ft`.

## Python API

```python
from cadmetrics import measure, project, sweep

metrics = measure("model.stl")
single = project("model.stl", alpha_deg=10)
rows = sweep("model.stl", alpha="-10:20:1", beta="-5:5:1", roll="0")
```

The Python API keeps lower-level `alpha`, `beta`, `roll`, and `direction` arguments. The CLI and
GUI present these as explicit `alpha-beta`, `roll-pitch`, and `vector` input modes.

## Documentation

- [CLI Usage](docs/cli.md)
- [GUI Usage](docs/gui.md)
- [Attitude Definition](docs/attitude.md)
- [Accuracy Notes](docs/accuracy.md)
- [Sample Geometry](docs/samples.md)
- [Fusion 360 Validation Notes](docs/fusion_validation.md)
- [Requirements](docs/requirements.md)
- [Release Process](docs/release.md)

## Accuracy Notes

STL measurements are mesh-based. STEP volume and surface area use the OCP/OpenCascade CAD
kernel when the `step` extra is installed. STEP projected area is calculated from a tessellated
mesh, so the result depends on tessellation quality.

The default `--mesh-deflection auto` uses the STEP bounding-box diagonal times `1e-5` in the
selected output length unit. The current validation target is within `0.1%` against Fusion 360
for representative closed solids.

See [Accuracy Notes](docs/accuracy.md) for details.

## Project Status

The first milestone focuses on a practical local workflow for one model at a time. Deferred
items include multi-model display, geometry repair, and Excel/HTML reports.

## License

MIT. See [LICENSE](LICENSE).
