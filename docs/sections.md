# Cross Sections and the Area Rule

cadmetrics can calculate how the cross-sectional area of a model changes from nose to tail. This
curve, the *area distribution* S(x), is what the transonic and supersonic area rules look at:
the smoother it is, the lower the wave drag. Use it to find where the area grows too quickly, for
example where the wing joins the fuselage, and to compare design changes.

## What is calculated

cadmetrics cuts the model with a series of equally spaced planes along X and measures the area
inside each cut.

- **Mach 1** (default): the planes are normal to X. This is the area distribution used by
  Whitcomb's transonic area rule.
- **Above Mach 1**: the planes lean back at the Mach angle μ = asin(1/M), as used by Jones'
  supersonic area rule. Leaning planes cut the model differently depending on which side they
  lean toward, so cadmetrics cuts them at several *roll angles* θ around the X axis and gives one
  area distribution for each. θ = 0° leans toward +Y and θ = 90° toward +Z.

Every section area is the area of the cut seen along X, that is, projected onto the YZ plane.
`x` is where the cutting plane crosses the X axis (Y = Z = 0). At Mach 1 this is simply the X
position of the plane; above Mach 1 it runs past the ends of the model, because tilted planes
touch the model before and after the X axis does.

The first plane touches the front of the model and has zero area. The last plane gives the
section just in front of the rear end, so a flat base shows up as its full area.

Parts that overlap, such as a wing passing through a fuselage, are counted once.

## Run it

### GUI

1. Open a model.
2. Click `Sections` at the top of the left panel.
3. Set `Sections` (the number of cutting planes) and `Mach`. Above Mach 1, also set
   `Roll angles`, and check `Mirror-symmetric about XZ` if the left and right halves of the model
   are mirror images.
4. Click `Run Sections`.

The results appear below the 3D view as a chart of area against x, with one line per roll angle.
Click a point, or a table row, to show that cutting plane and the outline of the section in the
3D view. The section with the largest area is selected when the calculation finishes.

With a single line, `Sears-Haack` overlays the ideal shape for comparison as a dashed line (see
below). `Save CSV` saves every section, and `Save Image` saves the chart.

Switching back to `Projected area` keeps the section results, and the projected-area results are
kept while you work with sections.

### CLI

```bash
# 101 sections normal to X
cadmetrics sections model.step --out sections.csv

# Mach 1.6, 16 roll angles, left-right symmetric model
cadmetrics sections model.step --mach 1.6 --thetas 16 --symmetric --out sections.csv
```

A summary table is printed after the calculation. See [Using the CLI](cli.md#sections).

### Python

```python
from cadmetrics import sections

result = sections("model.step", mach=1.6, theta_count=16, symmetric=True)
print(result.wave_drag_area, result.sears_haack_drag_area)
for series in result.series:
    print(series.theta_deg, series.max_area, series.max_area_x)
```

See [Using Python](api.md#cross-sections).

## Settings

| setting | GUI | CLI | default | meaning |
|---|---|---|---|---|
| Sections | `Sections` | `--sections` | 101 | Number of cutting planes, 5 to 2001. |
| Mach | `Mach` | `--mach` | 1 | Mach number, 1 to 10. |
| Roll angles | `Roll angles` | `--thetas` | 16 | Number of equally spaced roll angles, above Mach 1 only. |
| Symmetric | `Mirror-symmetric about XZ` | `--symmetric` | off | Cut about half the roll angles and count each one twice. Needs an even number of roll angles. |

### How many roll angles

The roll angles are spaced evenly around the full circle, which makes their average very
accurate. **16** is enough for most aircraft. Slender bodies such as rockets need fewer (8). Wide
spans, high Mach numbers, or nacelles and fins far from the axis may need 24 to 36. To check, run
again with twice as many roll angles: if the mean wave drag hardly changes, you have enough.

With `Mirror-symmetric about XZ`, 16 roll angles take 9 calculations instead of 16.

The number of sections usually matters more than the number of roll angles. Keep at least about
100 for wave drag.

## Reading the results

| value | meaning |
|---|---|
| Max area, at x | The largest section area, and where it is. |
| ∫S dx | The area integrated along x. For a closed model it equals the model volume, so a large difference points to a problem, such as a hole in the mesh. A blunt nose or base makes it slightly smaller, because the area jumps between two planes there. |
| Wave drag D/q | The zero-lift wave drag divided by the dynamic pressure, from slender-body theory, in the square of the output unit. Above Mach 1 it is averaged over the roll angles. Divide by a reference area to get a drag coefficient. |
| Sears-Haack | The body with the lowest possible wave drag for the same length and volume. Its area curve is the dashed line in the chart, and its D/q is shown for comparison. A ratio close to 1 means the area distribution is close to ideal. |

The wave drag is an estimate for comparing designs, not a prediction of the real drag:

- It comes from linear slender-body theory, which assumes a slender, smooth body. It is most
  reliable for long, pointed shapes.
- It assumes a pointed nose. If the model starts with a blunt face, cadmetrics warns that the
  value is not meaningful.
- At Mach 1 it is the limit of the supersonic theory, useful as an index of how smooth the area
  distribution is.
- Engine intakes are not handled: the air flowing through an intake should be subtracted from
  the area, and cadmetrics measures solid geometry only.
- Only the wave drag at zero lift is included; skin friction and lift-dependent drag are not.

## Result columns

Section results have their own CSV columns, one row per cutting plane:

| column | meaning |
|---|---|
| `mach` | Mach number. |
| `theta_deg` | Roll angle; empty at Mach 1. |
| `theta_weight` | Weight of this roll angle in the mean wave drag. The weights add up to 1. |
| `station` | Number of the cutting plane, from 1. |
| `x` | Where the plane crosses the X axis. |
| `area` | Section area, projected onto the YZ plane. |
| `area_slope` | How fast the area changes, dArea/dX. |
| `sears_haack_area` | Area of the matching Sears-Haack body at this x. |
| `wave_drag_area` | Wave drag D/q of this roll angle. |
| `sears_haack_drag_area` | D/q of the matching Sears-Haack body. |
| `mean_wave_drag_area` | D/q averaged over all roll angles. |
| `open_section` | `True` when the plane crosses a hole in the mesh, so the area may be too small. |

The file, unit, component, mesh, method, version, and warning columns mean the same as in
[Result Columns](results.md).

## Tips

- Sections are cut through the triangle mesh, so the [mesh settings](accuracy.md) affect them
  the same way they affect projected area.
- The X axis must run from nose to tail. If your model uses other axes, set the
  [axis map](concepts.md#coordinate-system).
- A mesh with holes gives sections that cannot be closed. Their area is too small, and
  cadmetrics warns about them. Repair the mesh in your CAD or mesh tool.
