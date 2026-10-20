# Troubleshooting

Warnings appear in the `warnings` column, in the GUI's `Model Details`, and in the output of
`cadmetrics inspect`. A warning does not stop the calculation; it tells you that a value may be
missing or less reliable.

## Values are off by large scale factors

The input unit may be wrong. STL files do not store a unit, so cadmetrics assumes meters. If
the STL was exported in millimeters, set the input unit to `mm` (GUI `Input unit`, CLI
`--unit mm`). With the same output unit, reading millimeter coordinates as meters makes lengths
1000 times too large, areas 1,000,000 times too large, and volumes 1,000,000,000 times too large.
Also check the output unit; its square is used for areas and its cube for volumes.

## Projected area is for the wrong side of the model

The model's axes probably differ from cadmetrics' X aft, Y right, Z up. Use the axis map to fix
this without changing the file. See [Coordinate system](concepts.md#coordinate-system).

## Volume is empty

Volume needs a closed (watertight) shape. Related warnings:

- `Mesh is not watertight; volume is unavailable.` The STL has holes or gaps.
- `Mesh face winding is inconsistent; volume is unavailable.` Some STL triangles face the wrong
  way.
- `STEP shape is open, invalid, or contains non-solid faces; volume was left unset.` The STEP file
  contains open surfaces or invalid solids.
- `STEP shape has zero volume; it may be open or surface-only geometry.`

Surface area and projected area are still calculated. To get the volume, repair the model in your
CAD or mesh tool and export it again.

## Base area is 0

`Could not find an Xmax base face; base_area set to 0.` The model has no flat face at its rear end
(the largest X). This is normal for rounded rear ends. If you expected a base face:

- check the axis map: the rear of the model must point to +X
- for a slightly uneven mesh, try a slightly larger `Base tolerance`

In `Subtract unchecked` mode, faces created by the cut are never counted as base area. If the cut
creates the whole rear face, base area is `0`.

## Overlapping parts may be counted twice

`Could not boolean-union ...; volume and surface area may double-count overlaps.` cadmetrics could
not merge the STEP solids into one. Volume and surface area may count overlapping regions twice;
projected area is not affected. Try fixing the overlapping or touching parts in your CAD tool, or
exclude parts that are not needed.

STL files are never merged, so overlapping STL parts always count the overlap twice in volume and
surface area. See [Several files as one model](concepts.md#several-files-as-one-model).

## Unit warnings for STEP files

- `Could not detect STEP length unit ...; assuming m.` The file does not say which unit it uses.
  Set the input unit yourself.
- `STEP length unit '...' is not available as an input unit; OpenCascade converted it to mm.` The
  file uses a unit cadmetrics does not list. The values have been converted correctly; you do not
  need to do anything.
- `Cannot assemble STEP files with different detected units` The files declare different units.
  If those units are correct, re-export the files from your CAD tool in a common unit, preserving
  their physical sizes and positions, then use `auto`. Set one explicit input unit only when the
  numeric coordinates already use that same unit and the declarations are wrong: an override
  reinterprets the numbers rather than converting each file from its declared unit.

## Other warnings

- `Could not calculate exact STEP base area; used tessellated mesh fallback.` Base area was
  calculated from the mesh instead of the exact geometry, so it depends slightly on the mesh
  settings.
- `STEP volume and surface area were calculated from the tessellated mesh.` This is expected with
  `--step-metrics mesh` (GUI `STEP metrics` `Mesh`).
- `Could not classify STEP cut faces; surface_area was left unset.` In subtract mode, cadmetrics
  could not tell the original faces from the faces created by the cut, so surface area is left
  empty rather than reported wrongly.

## Errors that stop the calculation

| message | what to do |
|---|---|
| `Cannot assemble mixed STEP and STL inputs.` | Open only STEP files or only STL files at once. |
| `Unsupported file type ...` | Use `.stl`, `.step`, or `.stp` files. |
| `Sweep would generate ... combinations; the maximum is 10,000.` | Use larger steps or a smaller range, or split the sweep. |
| `Sweep step must be positive when end is greater than start` | Use a positive step, or a negative step when counting down. |
| `step_component_mode='subtract' is only available for STEP input.` | Subtract mode works only with STEP files. |
| `STEP component subtraction produced an empty shape.` | The unchecked components cover all of the checked ones. Check the selection. |

In the GUI, `Run Sweep` is disabled while an input is invalid, and the reason is shown just above
the button.

## Calculations are slow

- Keep the default mesh setting (`auto`, GUI `Fast`) while exploring, and switch to
  `auto-precise` only for final numbers.
- Reduce the number of directions: use larger angle steps first, then refine around interesting
  angles.
- Exclude components that do not matter for the result.
- `measure` and `inspect` are faster than `project` and `sweep` for STEP files, because they do
  not need a mesh.

In the GUI, `Cancel` stops a sweep after the current direction and keeps the finished rows.
