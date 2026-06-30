# cadmetrics

`cadmetrics` calculates volume, surface area, and projected area for STL and STEP files.
It provides a CLI, Python API, and PySide6 GUI suitable for aerodynamic projected-area checks.

## Scope

- Input: STL ASCII/Binary and STEP (`.step`, `.stp`)
- Output: CSV
- Default coordinate convention: X aft, Y right, Z up
- Euler convention for attitude sweeps: roll -> angle of attack -> sideslip
- `alpha`, `beta`, `roll`, and `pitch` describe the projection direction attitude, not the
  inclination angle of a sketch or measurement plane
- Projected area definition: orthographic 2D outline area with overlaps removed
- Default length unit: m
- STEP input length units are detected automatically by default; STL defaults to m

STEP support is provided through the optional `step` extra because it pulls in a CAD kernel.

## Install

From PyPI after release:

```bash
pip install cadmetrics
```

With optional STEP support:

```bash
pip install "cadmetrics[step]"
```

With the PySide6 desktop GUI:

```bash
pip install "cadmetrics[gui]"
cadmetrics-gui
```

With both STEP support and the GUI:

```bash
pip install "cadmetrics[step,gui]"
```

From a local checkout:

```bash
pip install .
pip install ".[step]"
pip install ".[gui]"
pip install ".[step,gui]"
```

For development with uv:

```bash
uv sync --extra step
```

For STL-only usage:

```bash
uv sync
```

For the PySide6 desktop GUI:

```bash
uv sync --extra gui
cadmetrics-gui
```

For STEP support and the GUI together:

```bash
uv sync --extra step --extra gui
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

CSV output includes the equivalent attitude representations for each projected-area row:
`alpha_deg`, `beta_deg`, `roll_deg`, `pitch_deg`, and the normalized unit vector
`direction_x`, `direction_y`, `direction_z`. It also includes the projected-area centroid as
2D projection-plane coordinates (`centroid_u`, `centroid_v`) and as a 3D marker position on the
projection plane through the model center (`centroid_x`, `centroid_y`, `centroid_z`).

## Attitude Definition

The projection direction is represented as a unit vector in model coordinates:

```text
d = (d_x, d_y, d_z)
```

For `alpha`/`beta` input, cadmetrics uses the direction generated from the aircraft-style
attitude convention with roll fixed to zero:

```text
d = (cos(alpha) cos(beta), -sin(beta), sin(alpha) cos(beta))
```

The equivalent angles written to CSV are recovered from the unit vector as:

```text
alpha = atan2(d_z, d_x)
beta  = asin(-d_y)
```

For the GUI `roll`/`pitch` input, `pitch` is the angle away from the +X direction and `roll`
is the azimuth around +X, measured from +Z toward +Y:

```text
pitch = atan2(sqrt(d_y^2 + d_z^2), d_x)
roll  = atan2(d_y, d_z)
```

Angles in the CLI/GUI are entered and reported in degrees. A direct `--direction x,y,z` input is
normalized first, then the equivalent `alpha`/`beta` and `roll`/`pitch` values are calculated
from the same formulas.

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

Sweep CSV output includes the effective projection direction vector, projected centroid,
equivalent attitude angles, tessellation settings, calculation method, and elapsed seconds for
each row.

## GUI

The PySide6 GUI is a local desktop tool for loading one STL/STEP file, inspecting the mesh,
running projected-area sweeps, and saving the result table as CSV. Choosing a file with Browse
loads and displays the shape immediately. The viewer can toggle transparency, mesh edge display,
and an overlay with the current conditions/results. The current 3D view can be exported as a PNG
image.

The GUI supports three attitude input modes: alpha/beta, roll/pitch, and unit-vector components.
Angle modes use separate Start, End, and Step fields. Unit vector mode is a single direction
without sweep. Selecting a result row points the camera along that case's projection direction
and updates the overlay.

The first GUI milestone intentionally keeps multi-model comparison, automated extrema search,
geometry repair, and Excel/HTML reports out of scope.
