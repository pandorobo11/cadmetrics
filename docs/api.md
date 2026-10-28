# Using Python

The Python API lets you run cadmetrics from your own scripts and notebooks. It gives the same
results as the GUI and the CLI.

```python
from cadmetrics import inspect_model, measure, project, sections, sweep
```

| function | what it does | returns |
|---|---|---|
| `measure(files, ...)` | volume, surface area, base area, and bounds | one `MeasurementRow` |
| `project(files, ...)` | projected area for one direction | one `MeasurementRow` |
| `sweep(files, ...)` | projected area for a range of angles | a list of `MeasurementRow` |
| `sections(files, ...)` | cross-sectional area distribution along X | a `CrossSectionResult` |
| `inspect_model(files, ...)` | load the model and report its details | a `ModelData` |

`files` is one path, or a list of paths that are treated as one model (see
[Several files as one model](concepts.md#several-files-as-one-model)).

## Measure a model

```python
row = measure("model.step", output_unit="mm")

print(row.volume)
print(row.surface_area)
print(row.base_area)
print(row.warnings)
```

A `MeasurementRow` has one attribute for each [result column](results.md), for example
`row.projected_area` or `row.alpha_deg`. Values that do not apply are `None`.

## Projected area for one direction

Choose the attitude mode with `attitude`. Angle arguments end in `_deg` because they are in
degrees.

```python
row = project("model.step", attitude="alpha-beta", alpha_deg=10, beta_deg=5)
row = project("model.step", attitude="roll-pitch", roll_deg=30, pitch_deg=10)
row = project("model.step", attitude="vector", direction="1,0,0")

print(row.projected_area)
```

Arguments from another mode cannot be mixed in. For example, `beta_deg` is rejected with
`attitude="roll-pitch"`, and `direction` is required with `attitude="vector"`. See
[Attitude Angles](attitude.md).

## Sweep a range of angles

Each angle accepts a number or a `"start:end:step"` range string. Every combination is
calculated:

```python
rows = sweep(
    "model.step",
    attitude="alpha-beta",
    alpha_deg="-10:20:1",
    beta_deg="-5:5:1",
)

for row in rows:
    print(row.alpha_deg, row.beta_deg, row.projected_area)
```

The range rules are the same as in the CLI: `end` is included when the steps land on it, and one
sweep can have at most 10,000 combinations. With `attitude="vector"`, `sweep` returns one row.

To follow progress, pass `progress_callback`. It is called with the number of finished rows, the
total, and the newest row:

```python
def progress(done, total, row):
    print(f"{done}/{total}: {row.projected_area}")


rows = sweep(
    "model.step",
    attitude="roll-pitch",
    roll_deg="0:90:15",
    pitch_deg=10,
    progress_callback=progress,
)
```

## Save results as CSV

`MeasurementRow.to_csv_row()` returns a dictionary with the same columns the CLI and GUI write:

```python
import csv

records = [row.to_csv_row() for row in rows]
with open("sweep.csv", "w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows(records)
```

## Cross sections

`sections` cuts the model with planes along X and returns a `CrossSectionResult`. See
[Cross Sections and the Area Rule](sections.md) for the background.

```python
result = sections("model.step", section_count=101, mach=1.6, theta_count=16, symmetric=True)

print(result.wave_drag_area)  # D/q averaged over the roll angles
print(result.sears_haack_drag_area)  # D/q of the matching Sears-Haack bodies
for series in result.series:  # one per roll angle; a single one at Mach 1
    print(series.theta_deg, series.weight, series.max_area, series.max_area_x)
    print(series.x, series.area)  # NumPy arrays of the cutting planes
```

Each `SectionSeries` also has `length`, `volume` (the area integrated along x),
`area_slope`, `wave_drag_area`, `sears_haack_area`, and `sears_haack_drag_area`.
`result.rows()` returns one `SectionRow` per cutting plane, and `SectionRow.to_csv_row()` gives
the same columns as the CLI and GUI. `progress_callback` is called with the number of finished
sections and the total.

## Check a model and its components

`inspect_model` loads the model and returns its details without calculating projected area:

```python
model = inspect_model(["fuselage.step", "wing.step"])

print(model.input_unit, model.output_unit)
print(model.x_min, model.x_max)
print(model.is_watertight)
print(model.component_names)
print(model.warnings)
```

Use the order of `component_names` to choose STEP components. Numbers start at 1:

```python
files = ["fuselage.step", "wing.step"]

row = project(files, attitude="alpha-beta", alpha_deg=10, step_components=(1, 3))

cut = measure(files, step_components=(1, 3), step_component_mode="subtract")
print(cut.surface_area)                # surfaces of the remaining body
print(cut.newly_exposed_surface_area)  # surfaces created by the cut
```

`step_component_mode="filter"` (the default) leaves the other components out;
`"subtract"` cuts them away. See [STEP components](concepts.md#step-components).

## Options

All four functions accept these keyword arguments:

| argument | default | meaning |
|---|---|---|
| `input_unit` | `"auto"` | Length unit of the model file. `"auto"` reads it from STEP files and uses `"m"` for STL. |
| `output_unit` | `"m"` | Unit for all results: `"m"`, `"mm"`, `"cm"`, `"in"`, or `"ft"`. |
| `axis_map` | `"x,y,z"` | Which of your model's axes become cadmetrics X, Y, Z, for example `"x,-z,y"`. |
| `step_components` | all | Tuple of 1-based STEP components to include. |
| `step_component_mode` | `"filter"` | `"filter"` or `"subtract"`. |
| `step_metric_source` | `"brep"` | Source of STEP volume and surface area: `"brep"` or `"mesh"`. |
| `mesh_deflection` | `"auto"` | STEP mesh fineness: `"auto"`, `"auto-precise"`, or a number in the output unit. |
| `angular_deflection` | `"auto"` | Largest angle between mesh triangles in radians, or `"auto"`. |
| `base_tolerance` | `1e-6` | How close to the rear end a face must be to count as base area, as a fraction of the model size. |

These match the CLI options of the same name (see [Using the CLI](cli.md#options)) and the GUI's
`Advanced` settings. For the mesh options, see [Accuracy and Mesh Settings](accuracy.md).

The installed version is available as `cadmetrics.__version__`.
