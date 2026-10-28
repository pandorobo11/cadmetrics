# Using the GUI

The cadmetrics GUI is a desktop app for opening STL or STEP models, checking them in 3D, running
projected-area sweeps, and saving the results as CSV.

![cadmetrics GUI showing a satellite STEP sweep](assets/gui-main.png)

## Start the GUI

Install cadmetrics with the GUI, and STEP support if you need it:

```bash
pip install "cadmetrics[step,gui]"
```

Then start it:

```bash
cadmetrics-gui
```

## Window layout

- **Left panel**: settings, from top to bottom:
    - `Projected area` / `Sections`: which calculation to run
    - `Setup`: file and units
    - `Attitude`: the directions to calculate (`Sections` with the `Sections` calculation)
    - `Components`: which STEP solids to include
    - `Shape Display`: what the 3D view shows
    - `Advanced`: axis map and mesh settings
    - `Model Details`: a summary of the loaded model
- **Bottom of the left panel**: the loaded model's name, `Run Sweep`, and `Cancel`
- **3D view** (right): the model, with view buttons above it
- **Results** (below the 3D view): the result table or chart
- **Status bar** (bottom): progress and messages

`Components`, `Shape Display`, `Advanced`, and `Model Details` are collapsed until you need them.
Click a section title to open or close it.

## Basic workflow

1. Open one or more STL files, or one or more STEP files.
2. Check `Input unit` and `Output unit`.
3. Choose the attitude mode and enter the angles.
4. Click `Run Sweep` (⌘R / Ctrl+R).
5. Click a row in the results to see that direction in the 3D view.
6. Click `Save CSV` (⌘S / Ctrl+S) to save the results.

## Open a model

Any of these opens a model:

- click `Browse`
- choose `File` > `Open…` (⌘O / Ctrl+O)
- drag files onto the window
- type a path in the `File` field and press Enter

To try cadmetrics on a sample model, choose `File` > `Open Sample…`. The file dialog opens in the
folder of [sample models](samples.md).

The model appears in the 3D view as soon as it loads. To open several files as one model, select
them together. They must all be STL or all be STEP (see
[Several files as one model](concepts.md#several-files-as-one-model)).

After a file opens, the `File` field shows only its name. Hover over it to see the full path.

## Set the units

- `Input unit`: the length unit of the model file. `auto` reads the unit from STEP files and
  assumes meters for STL files.
- `Output unit`: the unit for all results, the overlay, and CSV files.

STL files do not store a unit. If yours was exported in millimeters, choose `mm`.

## Set the attitude

Choose a `Mode` in the `Attitude` section:

- `Alpha / Beta`: angle of attack and sideslip
- `Roll / Pitch`: roll and pitch
- `Unit vector`: one direction given as X, Y, Z

For the angle modes, each angle has `Start`, `End`, and `Step` fields in degrees. cadmetrics
calculates every value from `Start` to `End` in steps of `Step`, for every combination of the two
angles. For example, alpha 0 to 90 step 5 and beta −10 to 10 step 5 gives 19 × 5 = 95 results.
The number of results is shown below the fields.

- To calculate a single angle, set `Start` and `End` to the same value. `Step` is then ignored.
- `End` is included when the steps land on it exactly. Otherwise the last value is the last step
  before `End`.
- One sweep can have at most 10,000 results.

`Unit vector` calculates exactly one direction. The vector does not need to have length 1, but it
cannot be (0, 0, 0).

See [Attitude Angles](attitude.md) for what each angle means.

## Run and cancel

Click `Run Sweep` (⌘R / Ctrl+R). Rows appear in the results as each direction finishes, and the
status bar shows progress.

If `Run Sweep` is disabled, the reason is shown just above it, for example a missing file, an
invalid step, a zero unit vector, or no component selected.

`Cancel` (⌘. / Ctrl+.) stops the sweep after the direction currently being calculated. Rows that
are already finished stay in the table. Loading a STEP file and merging solids cannot be
interrupted; if you close the window during one of these steps, the app waits for it to finish.

If you change a setting after a sweep, the old rows stay visible but are dimmed and marked
`Results are out of date — Run Sweep to update.` You can still look at them and save them; each
row keeps the settings it was calculated with. Opening a different model clears the results.
If the model was loaded again with other units, components, or axes for the other calculation
(projected area or sections), the old results are not drawn in the 3D view, because they would
not match the model shown.

## Read the results

### Table

The table starts with the columns most useful for checking results: attitude, projected area,
centroid, and the model values. Scroll sideways to see all columns.

- Click a row to point the 3D view along that row's direction and show its values in the overlay.
- Click a column header to sort.
- Press ⌘C / Ctrl+C to copy the selected row as tab-separated text (for pasting into a
  spreadsheet).
- Numbers are shown with 6 significant digits. CSV files keep full precision.
- Column headers include the unit, for example `Projected area (m²)`.

The `File` column is hidden because every row comes from the same loaded model. Copied rows and
CSV files still include it.

See [Result Columns](results.md) for the meaning of each column.

### Chart

Click `Chart` above the results to plot projected area against the swept angle. By default, the
angle with more values goes on the x axis; choose another angle in `X axis` to swap them. Each
value of the other angle becomes one line.

- Point at a point to see its values. Click it to select that row, just like in the table.
- Up to 8 lines get their own colors and a legend. With 9 to 24 lines, the lines go from light to
  dark blue in value order.
- Unit-vector results, a single direction, and sweeps with more than 24 lines cannot be charted;
  use the table instead.

`Save Image` saves the chart as PNG or SVG. SVG is useful for documents because it stays sharp
when scaled.

### Save the results

`Save CSV` (⌘S / Ctrl+S, also in the `File` menu) saves every result row with all columns, at full
precision.

## Cross sections

Click `Sections` at the top of the left panel to calculate the cross-sectional area
distribution for area-rule studies instead of projected area. The `Attitude` settings are
replaced by `Sections`, `Mach`, `Alpha`, `Beta`, and `Roll angles`, `Run Sweep` becomes `Run Sections`, and the
results area shows the section chart and table. Click a point or row to see that cutting plane
and the section outline in the 3D view. Each calculation keeps its own results when you switch.

See [Cross Sections and the Area Rule](sections.md).

## Use the 3D view

Use the mouse to move the view:

- drag to rotate
- scroll to zoom
- Shift-drag (or drag with the middle button) to pan

The buttons above the view show the model from `+X`, `-X`, `+Y`, `-Y`, `+Z`, or `-Z`, or from one
of two angled views: `-X-Y+Z` (from above) and `+X+Y-Z` (from below). Each label names the side
the camera looks from. The chosen view is kept when you open another model.

`Save Image…` above the view, or `File` > `Save View Image…` (⇧⌘S / Ctrl+Shift+S), saves the
current view as PNG.

After a sweep, selecting a result row points the view along that row's projection direction. The
red arrow shows the direction, and the yellow marker shows the centroid of the projected area.

### The overlay

The panel in the upper-left corner of the view shows the file, units, surface area, base area, and
volume. When a result row is selected, it also shows that row's attitude and projected area.
Values that are not available are shown as `n/a`.

### Shape Display options

Open `Shape Display` to change what the view shows.

Rendering:

- `Transparent`: draw the model see-through
- `Mesh edges`: draw the triangle edges
- `Feature edges`: draw sharp edges (on by default)

Annotations:

- `Overlay`: the value panel in the upper-left (on by default)
- `Detailed overlay`: add bounds and calculation details to the overlay
- `Grid`: coordinate grid with axis labels (on by default; also used in saved images)
- `Projection arrow`: the red direction arrow (on by default)
- `Centroid`: the yellow centroid marker (on by default)
- `Base face`: highlight the base face in yellow (available when one is found)
- `Newly exposed surface`: highlight surfaces created by subtraction in orange (available in
  `Subtract unchecked` mode when there are any)

## Choose STEP components

When a STEP file contains several solids, the `Components` section opens and lists them. Names
come from the STEP file; unnamed solids are listed as `Component 1`, `Component 2`, and so on.
With several files, the list is grouped by file name.

- Clear a checkbox to leave that solid out. `All` and `None` check or clear the whole list.
- Point at a name to highlight that solid in the 3D view (in violet, drawn on top so hidden parts
  can be found).
- Double-click a part in the 3D view to toggle its checkbox.
- With nine or more components, a `Filter components` field lets you narrow the list. `All` and
  `None` then act on the listed components only.

`Mode` decides what happens to unchecked components:

- `Exclude unchecked (default)`: they are left out.
- `Subtract unchecked`: they are cut away from the checked components. Faces created by the cut
  are shown in orange and reported as `newly_exposed_surface_area` instead of `surface_area`.

Changes are not applied immediately. The section title shows `Components · changes pending`, and
the 3D view shows a rough preview: checked parts in the model color, unchecked parts in faint grey
(or translucent red when subtracting). The preview does not perform the cut, and the overlay
values still describe the applied selection. Click `Apply & Reload` to apply the change, or just
click `Run Sweep`, which applies it too.

The checked components are saved in the `step_components` and `step_component_names` columns, so
you can always tell which parts a result includes. Component selection is available for STEP
files only.

## Advanced settings

Open `Advanced` when you need to change the axes or the mesh settings. Changes are marked
`Advanced · changes pending` and are used on the next `Run Sweep`. Click `Apply & Reload` to
reload the model with them right away.

- `Axis map`: choose which of your model's axes becomes cadmetrics X, Y, and Z. Choose a minus
  sign, such as `-Z`, for an axis that points the other way. See
  [Coordinate system](concepts.md#coordinate-system).
- `STEP metrics`: where STEP volume and surface area come from. `B-Rep (default)` uses the exact
  CAD geometry. `Mesh` uses the generated triangle mesh, which is useful when comparing with an STL
  export.
- `Mesh quality`: `Fast (default)` is good for exploring many directions quickly. `Precise` makes a
  finer mesh for more accurate projected area but is several times slower.
- `Mesh deflection`: with `Auto` checked (default), follows `Mesh quality`. Uncheck `Auto` to enter
  the largest allowed gap between the true surface and the mesh, in the output unit.
- `Angular deflection`: with `Auto` checked (default), follows `Mesh quality` (`0.3`, or `0.1` with
  `Precise`). Uncheck `Auto` to enter the largest angle between neighboring mesh triangles, in
  radians.
- `Base tolerance`: how close to the rear end (largest X) a face must be to count as base area,
  as a fraction of the model size. The default `1e-6` rarely needs changing.

The mesh settings only affect STEP files. They change projected area and the 3D display, but not
the default B-Rep volume and surface area. See [Accuracy and Mesh Settings](accuracy.md) for
guidance.

## Model Details

`Model Details` shows a text summary of the loaded model: format, number of vertices and faces,
bounds, volume, surface area, base area, whether the shape is closed (`watertight`), the number of
selected components, and any warnings. Check it after loading if a value looks wrong; see
[Troubleshooting](troubleshooting.md) for common warnings.

## Open this documentation

Choose `Help` > `Documentation` to open this documentation in your web browser. It is included
with cadmetrics and works offline.
