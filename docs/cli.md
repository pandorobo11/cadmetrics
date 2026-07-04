# CLI Usage

`cadmetrics` provides four CLI commands:

- `measure`: volume and surface area
- `project`: projected area for one attitude or direction
- `sweep`: projected area for angle sweeps or one vector direction
- `inspect`: loaded model information

Install the base package for STL support:

```bash
pip install cadmetrics
```

Install STEP support when reading `.step` or `.stp` files:

```bash
pip install "cadmetrics[step]"
```

## Units

`--unit` describes the input model length unit. The default is `auto`:

- STEP: unit is read from the STEP file
- STL: unit is assumed to be `m`

`--output-unit` controls reported coordinate, area, and volume units.

Example: read a millimeter model and report SI units:

```bash
cadmetrics measure model.stl --unit mm --output-unit m
```

Supported explicit units are:

```text
m, mm, cm, in, ft
```

## Axis Mapping

Use `--axis-map` when the input model's axes do not match the cadmetrics convention. The value
lists the input axes to use as cadmetrics `X,Y,Z`:

```bash
cadmetrics project model.step --axis-map x,-z,y --alpha 10
```

In this example, cadmetrics `X` is input `X`, cadmetrics `Y` is input `-Z`, and cadmetrics `Z`
is input `Y`. Each source axis must be used exactly once. The default is `x,y,z`.

## measure

Calculate volume and surface area:

```bash
cadmetrics measure samples/unit_cube/unit_cube_ascii.stl
```

Without `--out`, `measure` prints a readable table to the terminal.

Write CSV:

```bash
cadmetrics measure samples/unit_cube/unit_cube.step --out measure.csv
```

Useful STEP options:

```bash
cadmetrics measure model.step \
  --step-metrics brep \
  --mesh-deflection auto \
  --angular-deflection 0.1
```

`--mesh-deflection auto` uses the STEP bounding-box diagonal times `1e-4` in the selected
output length unit.

`--step-metrics brep` is the default and reports STEP volume/surface area from the CAD kernel.
Use `--step-metrics mesh` when you want STEP volume/surface area to be calculated from the
tessellated mesh, for example when comparing with an exported STL.

## project

Choose one of three attitude input modes:

| mode | options |
|---|---|
| `alpha-beta` | `--alpha`, `--beta` |
| `roll-pitch` | `--roll`, `--pitch` |
| `vector` | `--direction x,y,z` |

Calculate projected area with alpha and beta:

```bash
cadmetrics project model.step --attitude alpha-beta --alpha 10 --beta 0
```

Without `--out`, `project` prints a readable table to the terminal. Use `--out` when CSV output
is needed.

Calculate projected area with roll and pitch:

```bash
cadmetrics project model.step --attitude roll-pitch --roll 0 --pitch 10
```

Calculate projected area from a unit-vector direction:

```bash
cadmetrics project model.step --attitude vector --direction 1,0,0
```

The direction vector is normalized before calculation.

## sweep

For `alpha-beta`, run every combination of `alpha` and `beta` values:

```bash
cadmetrics sweep model.step \
  --attitude alpha-beta \
  --alpha -10:20:1 \
  --beta -5:5:1 \
  --out sweep.csv
```

For `roll-pitch`, run every combination of `roll` and `pitch` values:

```bash
cadmetrics sweep model.step \
  --attitude roll-pitch \
  --roll 0:180:10 \
  --pitch 0:90:5 \
  --out sweep.csv
```

For `vector`, `sweep` returns one row because a unit vector is a single direction:

```bash
cadmetrics sweep model.step --attitude vector --direction 1,0,0
```

Ranges use inclusive `start:end:step` syntax. A single value is also valid. The sweep command
prints a progress bar to stderr and writes CSV rows to stdout unless `--out` is provided. Use
`--no-summary` to suppress the printed summary.

## inspect

Show loaded model information:

```bash
cadmetrics inspect model.step
```

This is useful for checking detected units, vertex and face counts, watertightness, and loader
warnings before running a sweep. For STEP files, it also reports the number of detected solid
components. Component on/off filtering is currently a GUI advanced feature.

## CSV Columns

All calculation commands use the same CSV schema:

| column | description |
|---|---|
| `file` | input path |
| `input_unit` | unit used when reading the model |
| `output_unit` | unit used for output values |
| `roll_deg` | equivalent roll angle |
| `pitch_deg` | equivalent pitch angle |
| `alpha_deg` | equivalent angle of attack |
| `beta_deg` | equivalent sideslip angle |
| `direction_x`, `direction_y`, `direction_z` | normalized projection direction |
| `x_min`, `x_max`, `y_min`, `y_max`, `z_min`, `z_max` | model coordinate bounds in `output_unit` |
| `surface_area` | surface area in `output_unit^2` |
| `volume` | volume in `output_unit^3` |
| `projected_area` | orthographic projected outline area in `output_unit^2` |
| `centroid_u`, `centroid_v` | projected 2D centroid in the projection plane |
| `centroid_x`, `centroid_y`, `centroid_z` | corresponding 3D marker position |
| `is_watertight` | mesh watertightness when known |
| `mesh_deflection` | effective STEP tessellation deflection, if applicable |
| `angular_deflection` | effective STEP angular deflection, if applicable |
| `method` | calculation backend summary |
| `elapsed_sec` | elapsed time for the row |
| `cadmetrics_version` | package version used for the calculation |
| `cadmetrics_hash` | git commit hash used for the calculation, with `-dirty` when tracked files differ |
| `warnings` | semicolon-separated warnings |

## Examples

Measure the sample satellite model in millimeters:

```bash
cadmetrics measure samples/satellite/satellite.step --output-unit mm
```

Project from a direction equivalent to `alpha=60 deg`:

```bash
cadmetrics project samples/satellite/satellite.step \
  --attitude vector \
  --output-unit mm \
  --direction 0.5,0,0.8660254
```

See also:

- [Attitude definition](attitude.md)
- [Accuracy notes](accuracy.md)
- [Sample geometry](samples.md)
