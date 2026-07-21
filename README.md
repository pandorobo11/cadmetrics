# cadmetrics

`cadmetrics` calculates volume, surface area, Xmax base-face area, and projected area for STL and STEP files.
It provides a CLI, Python API, and PySide6 desktop GUI for aerodynamic projected-area and
drag-area checks.

## Features

- Read STL ASCII/Binary and STEP (`.step`, `.stp`)
- Combine multiple STL files or multiple STEP files into one calculation model
- Calculate volume and surface area
- Calculate Xmax base-face area
- Calculate orthographic projected outline area with overlapping projected regions removed
- Sweep alpha/beta or roll/pitch angle ranges
- Report equivalent alpha/beta, roll/pitch, and unit-vector direction values
- Report projected-area centroids in 2D projection coordinates and 3D model coordinates
- Report model XYZ coordinate bounds in the selected output unit
- Report the cadmetrics package version and git hash used for each calculation
- Export CSV from CLI and GUI
- Inspect geometry in a local PySide6/PyVista GUI
- Toggle STEP solid components in the GUI advanced settings
- Optionally subtract disabled STEP components from enabled geometry
- Highlight surfaces newly exposed by component subtraction in the GUI

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

Combine same-format files as one model:

```bash
cadmetrics project fuselage.step wing.step tail.step \
  --attitude alpha-beta \
  --alpha 10
```

STEP files are boolean-unioned before measurement when possible. STL files are concatenated as
meshes without boolean repair, so overlapping STL parts can double-count volume and surface area.
STEP and STL files cannot be mixed in one calculation.

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
from cadmetrics import inspect_model, measure, project, sweep

metrics = measure("model.stl")
single = project("model.stl", attitude="alpha-beta", alpha_deg=10)
rows = sweep(
    "model.stl",
    attitude="alpha-beta",
    alpha_deg="-10:20:1",
    beta_deg="-5:5:1",
)

roll_pitch = project(
    "model.stl",
    attitude="roll-pitch",
    roll_deg=30,
    pitch_deg=10,
)

assembly = project(
    ["fuselage.step", "wing.step", "tail.step"],
    attitude="alpha-beta",
    alpha_deg=10,
)
components = inspect_model(["fuselage.step", "wing.step"]).component_names
filtered = project(["fuselage.step", "wing.step"], step_components=(1, 3))
cut = measure(
    "assembly.step",
    step_components=(1, 3),
    step_component_mode="subtract",
)
```

The Python API uses the same explicit `alpha-beta`, `roll-pitch`, and `vector` input modes as the
CLI and GUI. API angle names end in `_deg` to make their unit explicit.
For multi-file STEP component filtering, `step_components` uses the 1-based global order reported
by `inspect_model([...]).component_names`.

`step_component_mode="filter"` (the default) measures the union of enabled components.
`step_component_mode="subtract"` instead measures `Union(enabled) - Union(disabled)`. Its
`surface_area` excludes faces newly exposed by subtraction;
`newly_exposed_surface_area` reports those faces
separately. The CLI exposes the same behavior with repeatable `--step-component INDEX` options
and `--component-mode subtract`.
Newly exposed surfaces are also excluded from `base_area`; if they make up the entire final Xmax
plane, `base_area` is `0`.

## Documentation

- [CLI Usage](docs/cli.md)
- [Python API](docs/api.md)
- [GUI Usage](docs/gui.md)
- [Attitude Definition](docs/attitude.md)
- [Accuracy Notes](docs/accuracy.md)
- [Sample Geometry](docs/samples.md)
- [Fusion 360 Validation Notes](docs/fusion_validation.md)
- [Requirements](docs/requirements.md)
- [Release Process](docs/release.md)

## Accuracy Notes

STL measurements are mesh-based. STEP volume, surface area, and Xmax base-face area use the
OCP/OpenCascade CAD kernel when the `step` extra is installed. Multi-file STEP inputs are
boolean-unioned before measurement when possible. Multi-file STL inputs are mesh-concatenated
without boolean repair, so overlapping STL parts can double-count volume, surface area, and base
area. For STL-like comparisons, STEP volume and surface area can be calculated from the
tessellated mesh with `--step-metrics mesh`.
STEP projected area is always calculated from a tessellated mesh, so the result depends on
tessellation quality.
Open, invalid, or surface-only STEP shapes keep calculable area results but report no volume and
set `is_watertight` to false.
For faster large STEP checks, default B-Rep `measure` and CLI `inspect` skip tessellation when a
display/projected-area mesh is not needed. The GUI reuses the loaded display mesh when running a
sweep.

The default `--mesh-deflection auto` uses the STEP bounding-box diagonal times `1e-4` in the
selected output length unit. Xmax base-face detection uses `--base-tolerance 1e-6` by default,
applied as a relative tolerance to the model bounding-box diagonal. The current validation target
is within `0.1%` against Fusion 360 for representative closed solids.

See [Accuracy Notes](docs/accuracy.md) for details.

## Project Status

The first milestone focuses on a practical local workflow for one combined calculation model at a
time. Multiple input files are treated as one combined model. Excel/HTML reports and geometry
repair are out of scope; use CSV output and repair invalid CAD or mesh geometry in CAD/mesh tools
before using cadmetrics.

## License

MIT. See [LICENSE](LICENSE).
