# GUI Usage

The PySide6 GUI is a local desktop tool for loading one STL or STEP file, checking the shape,
running projected-area sweeps, and saving CSV results.

## Install

Install the GUI extra:

```bash
pip install "cadmetrics[gui]"
```

Install STEP support and the GUI together:

```bash
pip install "cadmetrics[step,gui]"
```

From a development checkout:

```bash
uv sync --extra step --extra gui
uv run cadmetrics-gui
```

## Launch

```bash
cadmetrics-gui
```

If using the local macOS helper app from the repository root:

```bash
open dist/Cadmetrics.app
```

## Basic Workflow

1. Click `Browse` and choose an STL or STEP file.
2. Confirm input and output units.
3. Adjust tessellation settings if needed.
4. Choose the attitude input mode.
5. Run `Run Sweep`.
6. Select rows in the result table to update the camera and overlay.
7. Save results with `Save CSV`.

The selected file is loaded and displayed immediately after browsing.

## Setup

`Input unit` defaults to `auto`.

- STEP files: unit is read from the file
- STL files: unit is assumed to be meters

`Output unit` controls displayed and exported length, area, and volume units.

## Advanced

`Advanced` is collapsed by default because these settings are usually changed less often.
Expand it when the loaded CAD axes or STEP tessellation settings need adjustment.

### Axis Map

`Axis map` remaps the loaded model axes before calculation and display. Choose which input axis
becomes cadmetrics `X`, `Y`, and `Z`. Use signs such as `-Z` when an axis is reversed. Changing
the combo boxes does not reload the model immediately; click `Apply`, browse a file, or run a
calculation to use the new mapping.

### Tessellation

`Mesh deflection` controls STEP tessellation used for projected-area calculations. `Auto`
is enabled by default and uses:

```text
bounding-box diagonal * 1e-5
```

`Angular deflection` controls STEP angular tessellation tolerance. Its default is `0.1`.

## Shape Display

The 3D view supports:

- transparent shape display
- mesh-edge display
- feature-edge display
- overlay text with current conditions or selected result values
- PNG export with `Save Image`

The viewer uses parallel projection. After a calculation, selecting a result row points the
camera along that row's projection direction.

## Attitude Input

The GUI supports three input modes:

- `Alpha / Beta`: sweeps angle of attack and sideslip
- `Roll / Pitch`: sweeps roll and pitch
- `Unit vector`: calculates one explicit projection direction

Angle modes use separate `Start`, `End`, and `Step` fields. The sweep calculates every
combination of the selected angle ranges. Unit-vector mode does not sweep.

See [Attitude Definition](attitude.md) for the coordinate convention and formulas.

## Results

The result table uses the same columns as the CLI CSV output. Important fields include:

- `projected_area`
- `centroid_u`, `centroid_v`
- `centroid_x`, `centroid_y`, `centroid_z`
- `alpha_deg`, `beta_deg`
- `roll_deg`, `pitch_deg`
- `direction_x`, `direction_y`, `direction_z`

The yellow centroid marker is shown when a projected-area result row is selected. The red
projection arrow is placed outside the model and aligned with the selected projected centroid
when available.

## Current Scope

The first GUI milestone supports one loaded model at a time. The following items are deferred:

- multiple model display
- automated maximum/minimum projected-area search
- geometry repair
- Excel and HTML reports
