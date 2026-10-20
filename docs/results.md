# Result Columns

Every result has the same fields, whether it comes from the GUI, the CLI, or the Python API. The
fields below are grouped by purpose, not by CSV column order. Use the CSV header to identify each
column. Lengths, areas, and volumes use the output unit (`output_unit`), its square, and its cube.
An empty cell means the value does not apply or could not be calculated.

## Input and settings

| column | meaning |
|---|---|
| `file` | The input file. Several files are separated by semicolons. |
| `step_components` | Numbers of the STEP components included, separated by commas. Empty for STL. |
| `step_component_names` | Names of those components, separated by semicolons. |
| `input_unit` | Unit used to read the model. |
| `output_unit` | Unit of the results. |

## Direction

| column | meaning |
|---|---|
| `attitude` | How the direction was given: `alpha-beta`, `roll-pitch`, or `vector`. Empty for `measure`. |
| `roll_deg`, `pitch_deg` | Roll and pitch in degrees. |
| `alpha_deg`, `beta_deg` | Angle of attack and sideslip in degrees. |
| `direction_x`, `direction_y`, `direction_z` | The direction as a vector of length 1. |

Every row reports the direction in all three forms. The angles of the mode you used are kept
exactly as you entered them; the others are calculated from the direction. See
[Attitude Angles](attitude.md#how-results-report-the-direction).

## Model size and shape

| column | meaning |
|---|---|
| `x_min`, `x_max` | Smallest and largest X coordinate of the model. |
| `y_min`, `y_max` | Smallest and largest Y coordinate. |
| `z_min`, `z_max` | Smallest and largest Z coordinate. |
| `surface_area` | Outer surface area. In subtract mode, surfaces created by the cut are not included. |
| `newly_exposed_surface_area` | Area of the surfaces created by the cut in subtract mode. Empty otherwise. |
| `base_area` | Area of the flat faces at the rear end (largest X). `0` with a warning when there is no such face. |
| `volume` | Volume. Empty when the shape is not closed. |
| `is_watertight` | `True` when the shape is closed, so its volume can be calculated. |

## Projected area

| column | meaning |
|---|---|
| `projected_area` | Silhouette area seen along the direction. Overlapping parts are counted once. |
| `centroid_u`, `centroid_v` | Center of the silhouette, in 2D coordinates on the projection plane. |
| `centroid_x`, `centroid_y`, `centroid_z` | The same center as a 3D point in model coordinates (where the GUI draws the yellow marker). |

These columns are empty for `measure`.

## Calculation details

| column | meaning |
|---|---|
| `mesh_deflection` | Mesh fineness actually used for STEP files, in the output unit. |
| `angular_deflection` | Mesh angle limit actually used for STEP files, in radians. |
| `base_tolerance` | Tolerance used to find the base face. |
| `step_component_mode` | `filter` or `subtract` for STEP files. |
| `method` | How the values were calculated, for example `step-brep`. |
| `load_elapsed_sec` | Seconds spent loading and preparing the model. |
| `elapsed_sec` | Seconds spent calculating this row. |
| `cadmetrics_version` | cadmetrics version used. |
| `cadmetrics_hash` | Source code revision used. `-dirty` means the source had local changes. |
| `warnings` | Warnings, separated by semicolons. See [Troubleshooting](troubleshooting.md). |

For a single `measure` or `project`, the total time is `load_elapsed_sec` plus `elapsed_sec`. In
a sweep, all rows share the same `load_elapsed_sec`, and each row has its own `elapsed_sec`.

`cadmetrics_version` and `cadmetrics_hash` let you trace any saved result back to the exact
software that produced it.
