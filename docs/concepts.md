# Key Concepts

This page explains the ideas you need to read cadmetrics results correctly. The GUI, the CLI, and
the Python API all follow the same rules.

## What cadmetrics measures

| value | what it means | result column |
|---|---|---|
| Volume | The volume enclosed by the model. Only available for closed (watertight) shapes. | `volume` |
| Surface area | The total area of the model's outer surface. | `surface_area` |
| Base area | The area of the flat faces at the very rear of the model (the largest X position). Useful as the base area for base-drag estimates. | `base_area` |
| Projected area | The area of the model's silhouette when you look at it along one direction. | `projected_area` |
| Projected centroid | The center of that silhouette. | `centroid_u`, `centroid_v`, `centroid_x/y/z` |
| Bounds | The smallest and largest X, Y, and Z coordinates of the model. | `x_min` … `z_max` |

Projected area is the outline area only. Where parts of the model overlap in the view, that area
is counted once, which is what you want for drag-area screening.

Area values use the square of the output unit (for example m²) and volume uses its cube (m³).
See [Result Columns](results.md) for every column.

## Coordinate system

cadmetrics assumes the following axes for the model:

```text
X: aft (toward the rear)
Y: right
Z: up
```

The rear of the model is therefore at the largest X value, which is where the base area is
measured.

If your CAD model uses different axes, you do not need to change the CAD file. Use the axis map
to tell cadmetrics which of your axes is its X, Y, and Z:

- GUI: `Advanced` > `Axis map`
- CLI: `--axis-map` (for example `--axis-map x,-z,y`)
- Python: `axis_map="x,-z,y"`

`x,-z,y` means: cadmetrics X is your X, cadmetrics Y is your −Z, and cadmetrics Z is your Y. Each
of your axes must be used exactly once.

## Projection direction and attitude

Projected area depends on the direction you look from. cadmetrics calls this the projection
direction, and you can give it in three ways:

- **Alpha / Beta**: angle of attack and sideslip, as used in aerodynamics
- **Roll / Pitch**: how far the direction tilts away from +X (pitch) and around which side
  (roll)
- **Unit vector**: the direction as `x, y, z` numbers

With all angles at 0 the direction is +X, so you see the model from the front. The angles
describe the direction you look from, not a rotation of the model.

In the GUI and with the CLI `sweep` command you can give a range of angles. cadmetrics then
calculates every combination, for example every alpha from 0 to 90° for every beta from −10 to
10°. One calculation is limited to 10,000 combinations.

See [Attitude Angles](attitude.md) for the exact definitions and formulas.

## Units

- **Input unit** is the length unit of the model file. The default `auto` reads the unit from a
  STEP file and assumes meters for STL, because STL files do not store a unit.
- **Output unit** is the unit used for all results. The default is `m`.

Supported units are `m`, `mm`, `cm`, `in`, and `ft`.

STL files exported in millimeters are common. In that case, set the input unit to `mm`, or every
value will be 1000 times too large. For STEP files, keep `auto` unless you know the unit stored in
the file is wrong: an explicit input unit reinterprets the numbers in the file.

## STEP and STL files

cadmetrics reads STL (ASCII and binary) and STEP (`.step`, `.stp`) files. STEP support needs the
`step` extra (`pip install "cadmetrics[step]"`).

- **STEP** files hold exact CAD geometry. Volume, surface area, and base area are calculated from
  that exact geometry by default.
- **STL** files hold a triangle mesh, so every value is calculated from the triangles.

Projected area is always calculated from a triangle mesh. For STEP files cadmetrics generates
that mesh itself, and its fineness affects the result slightly. See
[Accuracy and Mesh Settings](accuracy.md).

## Several files as one model

You can open several files at once. cadmetrics treats them as one combined model, for example a
fuselage, wings, and tail stored in separate files.

- All files must be the same format: STEP and STL cannot be mixed.
- **STEP** files are merged into one solid before measuring, so places where parts overlap are
  counted only once.
- **STL** files are simply put together. Where parts overlap, volume and surface area count the
  overlap twice. Projected area is still correct, because overlaps in the silhouette are counted
  once.

## STEP components

A STEP file often contains several solid bodies, called components here. You can choose which
of them to include:

- GUI: the `Components` section
- CLI: `--step-component INDEX` (repeat it for each component)
- Python: `step_components=(1, 3)`

Components are numbered from 1. With several files, numbering continues across files in the
order you gave them. Use the GUI list or `cadmetrics inspect` to see the numbers and names.

There are two ways to treat the components you leave out:

- **Exclude** (default): they are simply left out.
- **Subtract**: they are cut away from the components you keep. Use this, for example, to remove
  a cavity or a mounting part from the main body.

Subtracting can create new faces where material was cut away. These *newly exposed surfaces*
are not included in `surface_area` or `base_area`. Their area is reported separately as
`newly_exposed_surface_area`, and the GUI highlights them in orange.

## What cadmetrics does not do

- It does not repair broken geometry. Fix open, self-intersecting, or otherwise invalid models in
  your CAD or mesh tool first.
- It measures one combined model at a time.
- It writes results as CSV; it does not create Excel or HTML reports.
