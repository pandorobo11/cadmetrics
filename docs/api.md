# Python API

The public Python API provides model inspection, measurement, single-attitude projection, and
attitude sweeps:

```python
from cadmetrics import inspect_model, measure, project, sweep
```

## Projection attitudes

`project` and `sweep` use the same three attitude modes as the CLI and GUI. Python angle argument
names end in `_deg` to make the unit explicit.

### Alpha / Beta

```python
row = project(
    "model.step",
    attitude="alpha-beta",
    alpha_deg=10,
    beta_deg=5,
)
```

### Roll / Pitch

```python
row = project(
    "model.step",
    attitude="roll-pitch",
    roll_deg=30,
    pitch_deg=10,
)
```

### Unit vector

```python
row = project(
    "model.step",
    attitude="vector",
    direction="1,0,0",
)
```

Arguments from different modes cannot be mixed. For example, `beta_deg` is rejected in
`roll-pitch` mode, and `direction` is required in `vector` mode.

## Sweeps

Each angle accepts a number, a numeric string, or an inclusive `start:end:step` range.

```python
rows = sweep(
    "model.step",
    attitude="roll-pitch",
    roll_deg="0:90:15",
    pitch_deg="0:30:5",
)
```

Alpha/Beta sweeps use the corresponding degree-suffixed arguments:

```python
rows = sweep(
    "model.step",
    attitude="alpha-beta",
    alpha_deg="-10:20:1",
    beta_deg="-5:5:1",
)
```

A vector sweep represents one direction and therefore returns one row:

```python
rows = sweep(
    "model.step",
    attitude="vector",
    direction="1,0,0",
)
```

Use `progress_callback` to receive the completed row for each orientation:

```python
def progress(index, total, row):
    print(index, total, row.roll_deg, row.pitch_deg, row.projected_area)


rows = sweep(
    "model.step",
    attitude="roll-pitch",
    roll_deg="0:90:15",
    pitch_deg=10,
    progress_callback=progress,
)
```

## Units and results

STEP input units are read from the file when `input_unit="auto"`. STL input defaults to meters.
Supported explicit units are `m`, `mm`, `cm`, `in`, and `ft`.

```python
row = measure("model.step", input_unit="auto", output_unit="mm")

print(row.volume)
print(row.surface_area)
print(row.base_area)
print(row.warnings)
```

`project` returns one `MeasurementRow`; `sweep` returns a list of them. Use
`MeasurementRow.to_csv_row()` when writing API results in the same schema as the CLI and GUI.

## Multiple STEP components

Component selection uses the 1-based global order returned by `inspect_model`:

```python
files = ["fuselage.step", "wing.step"]
model = inspect_model(files)

print(model.component_names)

row = project(
    files,
    attitude="alpha-beta",
    alpha_deg=10,
    step_components=(1, 3),
)
```
