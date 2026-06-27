# cadmetrics

`cadmetrics` calculates volume, surface area, and projected area for STL and STEP files.
The first milestone is a CLI and Python API suitable for aerodynamic projected-area checks.

## Scope

- Input: STL ASCII/Binary and STEP (`.step`, `.stp`)
- Output: CSV
- Default coordinate convention: X aft, Y right, Z up
- Euler convention for attitude sweeps: roll -> angle of attack -> sideslip
- `alpha`, `beta`, and `roll` describe the projection direction attitude, not the
  inclination angle of a sketch or measurement plane
- Projected area definition: orthographic 2D outline area with overlaps removed
- Default length unit: m
- STEP input length units are detected automatically by default; STL defaults to m

STEP support is provided through the optional `step` extra because it pulls in a CAD kernel.

## Install

```bash
uv sync --extra step
```

For STL-only usage:

```bash
uv sync
```

For the PySide6 desktop GUI:

```bash
uv sync --extra gui-pyside
cadmetrics-gui
```

## CLI

```bash
cadmetrics measure model.step --unit m --out result.csv
cadmetrics project model.stl --alpha 10 --beta 0 --roll 0 --out projected.csv
cadmetrics project model.stl --direction 1,0,0 --out projected.csv
cadmetrics sweep model.step --alpha -10:20:1 --beta -5:5:1 --roll 0 --out sweep.csv
cadmetrics inspect model.step
```

`--unit` describes the input model length unit. Its default is `auto`: STEP units are read
from the file and STL is assumed to be meters. `--output-unit` controls output values.
For example, `--unit mm --output-unit m` reads coordinates as millimeters and reports m2/m3.

For Fusion 360 checks, be careful with plane angles: a measurement plane inclined by `30 deg`
has a normal direction that may correspond to `--alpha 60`, depending on the construction.
Use `--direction x,y,z` when you want to avoid that ambiguity.

## Samples

Validation fixtures live in `samples/`. They include cube, rectangular box, sphere, cylinder,
overlapping projected boxes, open STL, and a frame with a through-hole. See
[docs/samples.md](docs/samples.md) for the full list and expected values. Fusion 360 comparison
notes are kept in [docs/fusion_validation.md](docs/fusion_validation.md).

## Python API

```python
from cadmetrics import measure, project, sweep

metrics = measure("model.stl")
single = project("model.stl", alpha_deg=10)
rows = sweep("model.stl", alpha="-10:20:1", beta="-5:5:1", roll="0")
```

## Accuracy Notes

STL measurements are mesh-based. STEP volume and surface area use the OCP/OpenCascade CAD
kernel when the `step` extra is installed; projected area is computed from a tessellated mesh
so the result depends on `--mesh-deflection`. The target validation tolerance is 0.1% against
Fusion 360 for representative closed solids.

Sweep CSV output includes the effective projection direction vector, tessellation settings,
calculation method, and elapsed seconds for each row.

## GUI

The optional PySide6 GUI is a local desktop tool for loading one STL/STEP file, inspecting the
mesh, running `measure`, `project`, or `sweep`, and saving the result table as CSV. It uses the
same Python API as the CLI. The 3D view shows model axes and the current projection direction.

The first GUI milestone intentionally keeps multi-model comparison, automated extrema search,
geometry repair, Excel/HTML reports, and the Streamlit prototype out of scope.
