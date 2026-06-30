# CLI Usage

`cadmetrics` provides four CLI commands:

- `measure`: volume and surface area
- `project`: projected area for one attitude or direction
- `sweep`: projected area for all combinations in attitude ranges
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

## measure

Calculate volume and surface area:

```bash
cadmetrics measure samples/unit_cube/unit_cube_ascii.stl
```

Write CSV:

```bash
cadmetrics measure samples/unit_cube/unit_cube.step --out measure.csv
```

Useful STEP options:

```bash
cadmetrics measure model.step \
  --mesh-deflection auto \
  --angular-deflection 0.1
```

`--mesh-deflection auto` uses the STEP bounding-box diagonal times `1e-5` in the selected
output length unit.

## project

Calculate projected area for one direction:

```bash
cadmetrics project samples/box_1x2x3/box_1x2x3.step --direction 1,0,0
```

Calculate projected area from attitude angles:

```bash
cadmetrics project model.step --alpha 10 --beta 0 --roll 0
```

`--direction x,y,z` overrides `--roll`, `--alpha`, and `--beta`. The direction vector is
normalized before calculation.

## sweep

Run every combination of `roll`, `alpha`, and `beta` values:

```bash
cadmetrics sweep model.step \
  --roll 0 \
  --alpha -10:20:1 \
  --beta -5:5:1 \
  --out sweep.csv
```

Ranges use inclusive `start:end:step` syntax. A single value is also valid:

```bash
cadmetrics sweep model.step --alpha 0 --beta 0 --roll 0
```

The sweep command prints a progress bar to stderr and writes CSV rows to stdout unless `--out`
is provided. Use `--no-summary` to suppress the printed summary.

## inspect

Show loaded model information:

```bash
cadmetrics inspect model.step
```

This is useful for checking detected units, vertex and face counts, watertightness, and loader
warnings before running a sweep.

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
| `centroid_u`, `centroid_v` | projected 2D centroid in the projection plane |
| `centroid_x`, `centroid_y`, `centroid_z` | corresponding 3D marker position |
| `volume` | volume in `output_unit^3` |
| `surface_area` | surface area in `output_unit^2` |
| `projected_area` | orthographic projected outline area in `output_unit^2` |
| `is_watertight` | mesh watertightness when known |
| `mesh_deflection` | effective STEP tessellation deflection, if applicable |
| `angular_deflection` | effective STEP angular deflection, if applicable |
| `method` | calculation backend summary |
| `elapsed_sec` | elapsed time for the row |
| `warnings` | semicolon-separated warnings |

## Examples

Measure the sample satellite model in millimeters:

```bash
cadmetrics measure samples/satellite/satellite.step --output-unit mm
```

Project from a direction equivalent to `alpha=60 deg`:

```bash
cadmetrics project samples/satellite/satellite.step \
  --output-unit mm \
  --direction 0.5,0,0.8660254
```

See also:

- [Attitude definition](attitude.md)
- [Accuracy notes](accuracy.md)
- [Sample geometry](samples.md)
