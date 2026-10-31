# Cross Sections and the Area Rule

cadmetrics can calculate how the cross-sectional area of a model changes from nose to tail. This
curve, the *area distribution* S(x), is what the transonic and supersonic area rules look at:
the smoother it is, the lower the wave drag. Use it to find where the area grows too quickly, for
example where the wing joins the fuselage, and to compare design changes.

## What is calculated

cadmetrics cuts the model with a series of equally spaced planes along the flow and measures the
area inside each cut. By default the flow runs along +X; see
[Flow direction](#flow-direction) to cut relative to the cruise attitude instead.

- **Mach 1** (default): the planes are normal to the flow. This is the area distribution used by
  Whitcomb's transonic area rule.
- **Above Mach 1**: the planes lean back at the Mach angle μ = asin(1/M), as used by Jones'
  supersonic area rule. Leaning planes cut the model differently depending on which side they
  lean toward, so cadmetrics cuts them at several *roll angles* θ around the flow and gives one
  area distribution for each. θ = 0° leans toward +Y and θ = 90° toward +Z.

Every section area is the area of the cut seen along the flow, that is, projected onto the plane
normal to the flow. `x` is where the cutting plane crosses the flow axis through the model
origin. With the flow along +X and at Mach 1 this is simply the X position of the plane; above
Mach 1 it runs past the ends of the model, because tilted planes touch the model before and after
the axis does.

The first plane touches the front of the model and has zero area. The last plane gives the
section just in front of the rear end, so a flat base shows up as its full area.

Parts that overlap, such as a wing passing through a fuselage, are counted once.

## Run it

### GUI

1. Open a model.
2. Click `Sections` at the top of the left panel.
3. Set `Sections` (the number of cutting planes) and `Mach`, and `Alpha` and `Beta` if the
   sections should follow the cruise attitude. Above Mach 1, also set `Roll angles`, and check
   `Mirror-symmetric about XZ` if the left and right halves of the model are mirror images.
4. Click `Run Sections`.

The results appear below the 3D view as a chart of area against x, with one line per roll angle.
Click a point, or a table row, to show that cutting plane and the outline of the section in the
3D view. The section with the largest area is selected when the calculation finishes.

- `Area` / `Slope` plots the section area or its slope dArea/dX against x (see
  [Area and slope](#area-and-slope)).
- `Terms` plots how much each part of the slope adds to the wave drag (see
  [Wave drag by term](#wave-drag-by-term)).
- Above Mach 1, `Roll angles` plots the wave drag of each roll angle, and `Roll angle` shows
  every roll angle or one of them (see [Roll angles above Mach 1](#roll-angles-above-mach-1)).
- `Sears-Haack` overlays the ideal body for comparison as a dashed line (see below). Against x,
  it needs a single line.

`Save CSV` saves every section, and `Save Image` saves the chart.

Switching back to `Projected area` keeps the section results, and the projected-area results are
kept while you work with sections.

### CLI

```bash
# 101 sections normal to X
cadmetrics sections model.step --out sections.csv

# Mach 1.6, 16 roll angles, left-right symmetric model
cadmetrics sections model.step --mach 1.6 --thetas 16 --symmetric --out sections.csv

# Relative to a cruise attitude of 3° angle of attack
cadmetrics sections model.step --mach 1.6 --alpha 3 --symmetric --out sections.csv
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
| Alpha | `Alpha` | `--alpha` | 0 | Angle of attack of the flow in degrees. |
| Beta | `Beta` | `--beta` | 0 | Sideslip angle of the flow in degrees. |
| Roll angles | `Roll angles` | `--thetas` | 16 | Number of equally spaced roll angles, above Mach 1 only. |
| Symmetric | `Mirror-symmetric about XZ` | `--symmetric` | off | Cut about half the roll angles and count each one twice. Needs an even number of roll angles and Beta 0. |

### Flow direction

The area rule is about how the model's area is arranged *along the flow*, so the sections should
be cut relative to the flow at the condition you are designing for, usually cruise. `Alpha` and
`Beta` give that flow direction with the same angles as the projected-area attitude
([Attitude Angles](attitude.md#alpha-and-beta)): the flow runs along
`(cos α cos β, −sin β, sin α cos β)`. Roll angles are measured around the flow, with θ = 90°
leaning toward the lift direction (normal to the flow, in the model's XZ plane).

What changes is mostly *where* the parts of the model meet the planes, not how big they are.
A part at height z above the axis moves by about z·sin α along the flow: at α = 3°, a fin tip 2 m
above the axis moves about 0.1 m. This matters most for tails, nacelles, and stores far above or
below the axis, and above Mach 1, where the Mach planes on the upper and lower sides lean
differently relative to the model.

Any angle can be used, but the area rule and the wave drag D/q assume that the flow runs nearly
along the body. Above 15° of alpha or beta, cadmetrics warns that the results are only a rough
reference; real cruise angles are a few degrees.

A flat base that is normal to X is no longer normal to the flow, so its area tapers to zero over
the last few planes instead of appearing at the last plane.

Lift is not included. With lift, the supersonic area rule adds a term from the lift distribution
to each equivalent body, which cadmetrics cannot know from the geometry.

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
| Sears-Haack | The minimum-wave-drag slender body for the same length and volume with zero area at both ends. Its area curve is the dashed line in the chart, and its D/q is shown for comparison. |

The Sears-Haack reference is not a lower bound for a body with a nonzero base area. Such a body
has different end conditions and can have a ratio below 1 without a calculation error. For
example, the von Karman ogive has one eighth of the Sears-Haack D/q for the same length and
volume under this theory. Compare ratios as an optimality measure only when the end conditions
match.

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

### Area and slope

The wave drag comes from how the *slope* of the area curve changes, not from the area itself.
cadmetrics writes the slope dArea/dX as a sum of sine waves along the body, the n-th wave having
n half-waves over the length, and the wave drag adds up the square of each wave's size times n:

```
D/q = π/4 · Σ n·Aₙ²     with dArea/dX = Σ Aₙ sin(nφ) and x = L (1 − cos φ) / 2
```

The Sears-Haack body is a single wave (n = 2). Every other wave adds drag, and short ones cost
more than long ones. That is why kinks and narrow bumps in the area curve matter more than a
smooth difference from the dashed line.

`Slope` shows this directly:

| line | meaning |
|---|---|
| Fitted (colored) | The sine series the wave drag is computed from. It is smooth and zero at both ends. |
| Differences (gray) | dArea/dX from neighbouring sections, as in the `area_slope` column. It shows every step and some mesh noise, and it is cut off at the edges of the chart where it runs far beyond the fitted line. |
| Sears-Haack (dashed) | The slope of the matching Sears-Haack body, a single smooth wave. |

What to look for:

- A **step** in the slope is a kink in the area curve, for example where a wing root starts.
- A **sharp swing** up and down is a narrow bump, for example a canopy or a wing over a short
  stretch of the body. Spreading it out along x lowers the drag.
- A **spike** in the differences is a jump in the area, such as a flat front face. It is the
  most expensive shape there is.
- Where the fitted line ripples around a step or spike, the series cannot follow a shape that
  sharp. The wave drag of such a model depends on the number of sections, so compare runs with
  the same `Sections`.
- Where the fitted line follows the dashed one closely, there is little to gain.

### Wave drag by term

`Terms` shows the wave drag of each term n of the sine series as a bar; the bars add up to D/q.
Above Mach 1 they are averaged over the roll angles, unless `Roll angle` picks one.

| terms | come from | to reduce them |
|---|---|---|
| n = 1 | The base area at the rear end. | A smaller base. |
| n = 2 | The overall size: how much volume the length holds. A Sears-Haack body has this term only; its D/q is the dashed outline. | Less maximum area, or a longer body. |
| higher n | The local shape: kinks, narrow bumps, and steps, the higher the sharper. | Smoothing the shape where the slope chart shows steps and swings. |

When the n = 2 bar is close to the dashed outline and most of the drag sits in higher terms,
the overall size is fine and the local shape is what to work on. When n = 2 dominates, smoothing
gains little; the body has to get slimmer or longer.

The highest terms can only follow features a few sections wide. A bar that is tall at the last
terms usually means a step or sharp kink that the series cannot resolve.

### Roll angles above Mach 1

Above Mach 1 each roll angle is its own equivalent body, and the wave drag is their weighted
mean. `Roll angles` plots the D/q of each roll angle against θ, with the D/q of its Sears-Haack
body (dashed) and the mean (gray). Click a point to choose that roll angle and show its largest
section. `Roll angle` lists each roll angle with its D/q and its share of the mean, and marks the
largest share. Improve those roll angles first.

Choose one roll angle to chart its line alone. Its Sears-Haack body, which has that roll angle's
length, can then be overlaid in `Area` and `Slope`, and `Terms` shows that roll angle alone.
Selecting a table row of another roll angle switches the chart to that roll angle.

For a wing that lies close to the XY plane, the planes that lean toward ±Z (θ = ±90°) cut the
wing almost as at Mach 1, so its area appears over a short stretch and the bump is sharpest.
The planes that lean toward ±Y (θ = 0° and 180°) cut the wing at an angle and spread its area
along x. These roll angles often differ most.

## Result columns

Section results have their own CSV columns, one row per cutting plane:

| column | meaning |
|---|---|
| `mach` | Mach number. |
| `alpha_deg`, `beta_deg` | Angle of attack and sideslip of the flow the sections are cut relative to. |
| `theta_deg` | Roll angle; empty at Mach 1. |
| `theta_weight` | Weight of this roll angle in the mean wave drag. The weights add up to 1. |
| `station` | Number of the cutting plane, from 1. |
| `x` | Where the plane crosses the flow axis through the origin. |
| `area` | Section area, projected onto the plane normal to the flow. |
| `area_slope` | How fast the area changes, dArea/dX, from the neighbouring sections. |
| `fitted_area_slope` | dArea/dX of the smooth sine series the wave drag is computed from. |
| `sears_haack_area` | Area of the matching Sears-Haack body at this x. |
| `sears_haack_area_slope` | dArea/dX of the matching Sears-Haack body. |
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
  [axis map](concepts.md#coordinate-system). Use `Alpha` and `Beta` for the flow direction, not
  the axis map.
- Parts whose faces point inward (an inside-out STL) count like the others, and cavities stay
  empty. If an inside-out part crosses another part so that cadmetrics cannot tell it from a
  cavity, a warning says the overlapping area is left out.
- Parts that touch or overlap along shared edges, for example separate STL files with mating
  faces, are joined into one shell. If one of them is inside out, cadmetrics cannot turn it
  around, so its sections may be partly or entirely missing. A warning is shown whenever parts
  share edges; it can be ignored when every part faces outward.
- A mesh with holes gives sections that cannot be closed. Their area is too small, and
  cadmetrics warns about them. Repair the mesh in your CAD or mesh tool.
