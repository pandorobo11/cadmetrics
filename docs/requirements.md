# cadmetrics Requirements

## Goal

Build a Python package for aerodynamic and drag-area evaluation by measuring CAD geometry
from STL and STEP files.

## Users

- Primary users: the author and design engineers with similar skill level
- Primary use case: aerodynamic projected-area and resistance-area evaluation

## MVP

- Manage the project with `uv`
- Provide a pip-installable Python package named `cadmetrics`
- Provide a CLI entry point named `cadmetrics`
- Provide an optional PySide6 GUI entry point named `cadmetrics-gui`
- Support STL ASCII/Binary and STEP input
- Calculate volume and surface area
- Calculate orthographic projected outline area
- Sweep all combinations of roll, angle of attack, and sideslip ranges
- Write CSV output
- Publish a Python API

## Geometry Scope

- STL is treated as mesh geometry
- STEP volume and surface area should use B-Rep calculations when the `step` extra is installed
- STEP projected area is calculated from a tessellated mesh
- Multiple solids are treated as one projected silhouette, so overlapping projected regions are
  counted once
- Open or non-watertight meshes are accepted with warnings; volume may be unreliable
- STEP assemblies and compounds are supported geometrically, but assembly metadata is not a
  first-version requirement
- Surface-only STEP geometry is allowed to load if tessellation succeeds, but volume may be zero
  or unavailable

## Units

- Default input length unit: `m`
- Input unit can be specified
- Output unit can be specified separately
- Area and volume are reported in the selected output unit squared and cubed

## Attitude Convention

- Default coordinate convention: X aft, Y right, Z up
- Angles follow an aircraft-style convention
- Rotation order: roll -> angle of attack -> sideslip
- CLI accepts single angle values or inclusive `start:end:step` ranges
- Sweep calculates every combination of roll, alpha, and beta
- Vector direction can be specified directly for single projected-area calculations
- `alpha`, `beta`, `roll`, and `pitch` describe the projection direction attitude. A Fusion
  360 sketch or measurement plane angle can be complementary because the projection direction
  is normal to that plane.
- Projected-area output reports equivalent alpha/beta, roll/pitch, and unit-vector direction
  values for each case.
- With normalized projection direction `d = (d_x, d_y, d_z)`, equivalent output angles are
  `alpha = atan2(d_z, d_x)`, `beta = asin(-d_y)`,
  `pitch = atan2(sqrt(d_y^2 + d_z^2), d_x)`, and `roll = atan2(d_y, d_z)`.

## CLI Shape

```bash
cadmetrics measure model.step --unit m --out result.csv
cadmetrics project model.stl --alpha 10 --beta 0 --roll 0 --out projected.csv
cadmetrics project model.stl --direction 1,0,0 --out projected.csv
cadmetrics sweep model.step --alpha -10:20:1 --beta -5:5:1 --roll 0 --out sweep.csv
cadmetrics inspect model.step
```

Default `--unit` is `auto`: STEP units are read from the file, and STL is assumed to be meters.

## GUI Shape

The first GUI is a PySide6 desktop application installed through the `gui` extra:

```bash
uv sync --extra gui
cadmetrics-gui
```

It supports one loaded model at a time, immediate shape display after Browse file selection, a
PyVista 3D view, unit controls, sweep execution, a progress bar, cancellation for sweep jobs, a
result table, and CSV export. GUI attitude input can be alpha/beta, roll/pitch, or unit-vector
components. Angle modes use separate Start, End, and Step fields. Unit-vector mode is a single
direction without sweep. The viewer supports transparency and mesh-edge toggles, a conditions
and results overlay, row-selection camera alignment, and PNG image export.

## CSV Columns

- `file`
- `input_unit`
- `output_unit`
- `roll_deg`
- `pitch_deg`
- `alpha_deg`
- `beta_deg`
- `direction_x`
- `direction_y`
- `direction_z`
- `volume`
- `surface_area`
- `projected_area`
- `is_watertight`
- `mesh_deflection`
- `angular_deflection`
- `method`
- `elapsed_sec`
- `warnings`

## Accuracy Target

- Target validation tolerance: 0.1% against Fusion 360 for representative closed solids
- Projected area depends on mesh/tessellation quality
- `--mesh-deflection` is exposed so STEP projected-area accuracy can be adjusted

## Deferred

- Multiple model display
- Excel and HTML report output
- Automated maximum/minimum projected-area search
- Geometry repair
