# Geometry Internals

Implementation details behind the user-facing [Accuracy and Mesh Settings](../docs/accuracy.md)
page. Keep user-visible behavior summarized there and the mechanisms here.

## STEP measurement backend

For STEP input (`cadmetrics[step]`, OCP/OpenCascade):

- volume uses `VolumePropertiesGK` after boolean-unioning multiple solids
- surface area uses the B-Rep model after boolean-unioning multiple solids
- base area uses B-Rep face area for exterior faces at cadmetrics-coordinate `Xmax`
- `--step-metrics mesh` instead calculates volume and surface area from the tessellated mesh after
  boolean union
- projected area always uses a tessellated mesh generated from the B-Rep
- component filters are applied to solids after loading and before boolean union

Before reporting STEP volume, cadmetrics validates that the shape contains valid closed solids
and no loose non-solid faces. Open, invalid, or surface-only STEP shapes report `volume=None` and
`is_watertight=False`; surface, base, and projected areas remain available when calculable.

OCP does not expose a separate `SurfacePropertiesGK` function. Surface area uses
`SurfaceProperties`; OCP's Python binding also exposes an adaptive-integration overload that
accepts an error tolerance, but cadmetrics currently keeps the default exact-surface call.

OpenCascade is kept in its standard millimetre system regardless of the input unit, because its
geometric tolerances are expressed in kernel coordinates and become unreliable for very small
models if the kernel itself is switched to metres or feet. Coordinates are scaled to the requested
input unit afterwards. An explicit `--unit` for a STEP file reinterprets the file's numbers in that
unit instead of the declared one.

Multi-file STEP input loads every file's solids into one compound before the same union step. With
`--unit auto`, all detected units must match; otherwise loading fails.

## Base area

`base_area` is the sum of exterior face areas whose coordinates lie on `Xmax` after applying the
axis map. Faces count when they are within `max(bounding-box diagonal * base_tolerance, 1e-12)`
of `Xmax` in the output length unit. Curved bodies that only touch `Xmax` at a point or line
report `0` with a warning. STL input approximates the same definition by summing triangle faces on
the `Xmax` plane. If the exact B-Rep base-area calculation fails, a tessellated mesh fallback is
used with a warning.

In STEP `subtract` mode, surfaces newly exposed by subtraction are excluded from `base_area`. The
Xmax position still comes from the final subtracted shape; if all faces at that position are newly
exposed, `base_area` is `0` and cadmetrics does not search inward for another plane. If
OpenCascade cannot provide usable face history, `surface_area` (or `base_area`) is left unset with
a warning instead of silently including generated faces.

## Boolean union checks

OpenCascade's general fuse can return a shape that passes its own validity checks but has a
badly wrong volume. This is known to happen where curved solids touch tangentially, for example
a torus resting against a cylinder. cadmetrics guards the union in two ways:

- The fuse runs with an absolute fuzzy tolerance of `1e-5` mm (in the kernel's millimetre units),
  which handles these near-coincidences. Gaps and overlaps smaller than this between solids may be
  treated as touching. The tolerance does not grow with the model size, so adding a distant part
  does not close real gaps between nearby parts.
- The result must pass OpenCascade's shape validity check and is then compared with the input
  solids at a few points per solid. Each solid contributes up to two points that its own classifier
  puts inside it. They are found along lines through points on its faces, so thin walls are
  sampled too. The union is rejected if it loses all of a solid's interior points, or if no
  interior point can be found for a solid. Each solid also contributes four random points in its
  bounding box, compared against all inputs, and more than 1% disagreement overall rejects the
  union. If either check fails or cannot run, the union is retried once with `1e-4` mm. If that
  also fails, the solids are measured without the union, with a "Could not boolean-union" warning:
  volume and surface area may then double-count overlaps. In `subtract` mode the load fails
  instead.

The check is probabilistic. Each solid is probed at only a few points, so the check reliably
catches a solid that disappears from the union and large misclassified regions, but it cannot prove
the union is exact. A solid that is only partly lost, small misclassified regions, or a
surface-area-only change such as faces wrongly merged across a gap below the fuzzy tolerance can
pass. It does not bound the measurement error.

## Projected area numerics

Positive projected polygons are retained without an absolute area cutoff, including areas
below `1e-15` in the output area unit. Degenerate projections report zero area and no centroid.
Angles that are exact multiples of 90 degrees use exact sine/cosine values, so axis-aligned
edge-on projections agree with equivalent explicit direction vectors. Nearby angles and small
nonzero vector components are not snapped to an axis; their positive projected areas are kept.
This does not remove floating-point precision limits or change STL import's vertex merging,
which can collapse very small features before projection.

The 3D centroid marker (`centroid_x/y/z`) is the projected 2D centroid placed on the projection
plane through the model center.

## Cross sections

`cadmetrics.sections` cuts the same triangle mesh that projected area uses. The user-facing
description is in [Cross Sections and the Area Rule](../docs/sections.md).

### Cutting planes

Everything below works in wind axes. `prepare_section_mesh` rotates the vertices with
`wind_axes(alpha, beta)`, which is `orientation.rotation_matrix` for roll 0: its first row is the
projection direction for the same alpha and beta, its third row the lift direction. Rotating
before welding is safe because equal input coordinates rotate to equal output coordinates, and a
rotation keeps areas and face orientation. Outlines are rotated back with `q @ axes`. With both
angles at 0 the vertices are used as they are, so results are bit-identical to the unrotated
code. Mirror symmetry about XZ survives a rotation about Y, so `symmetric` needs only beta = 0.

The planes are `n . p = x0` with `n = (1, -beta cos(theta), -beta sin(theta))` and
`beta = sqrt(M^2 - 1)`, so `x0` is where a plane crosses the X axis and Mach 1 gives planes normal
to X. A section's area is measured in YZ coordinates, which is the oblique cut projected along X
as Jones' supersonic area rule requires. Projection along X is a shear with unit Jacobian, so the
integral of every roll angle's S(x0) equals the model volume; the tests use that as a check.

The planes are spaced evenly from the smallest to the largest `n . p` on the mesh. A vertex
exactly on a plane counts as lying past it, which is symbolic perturbation of the plane toward
smaller `x0`. Every crossed triangle then has exactly one lone vertex and cuts exactly two edges,
coplanar faces are never cut, the first plane is empty, and the last plane gives the section just
in front of a flat base.

### Building a section without tracing loops

Vertices are welded by exact coordinates first (OCC's per-face triangulations share identical
boundary coordinates, as the projection's closed-surface check already relies on). Each crossing
point is computed from its edge with the edge's vertices in a fixed order, so both neighbouring
triangles produce bit-identical points.

For all planes of one roll angle at once, the code finds each triangle's range of crossed planes
with `searchsorted` on the per-face minimum and maximum, and expands them into (face, plane)
pairs. Each pair gives one segment between the crossing points on the two cut edges, oriented
from the triangle's winding: from the edge after the lone vertex to the edge before it when the
lone vertex lies past the plane, the other way otherwise. For a closed mesh with outward
counter-clockwise faces, that runs the section boundary counter-clockwise around +X.

Per plane, the segments are noded with `shapely.union_all` and split into faces with
`polygonize_full`. A face is inside the section when:

- the mesh is closed and consistently oriented: the winding number of an interior point of the
  face, from the oriented segments, is at least 1 (with the sign flipped for an inside-out mesh).
  Overlapping or duplicated bodies then count once, which is what multi-file STL assemblies and
  a STEP model whose union failed need;
- otherwise: the even-odd crossing count against the closed linework, with GEOS's dangles and cut
  edges removed. Sections with loose ends are flagged `open_section` and counted in a warning.

If GEOS cannot node a section even with a snap-rounding retry, the area falls back to the signed
shoelace sum of the segments and a warning says overlaps were not removed.

Reference timing on an M-series Mac: a 500k-triangle sphere takes about 0.5 s for 101 planes at
Mach 1 and about 4.5 s for 16 roll angles at Mach 1.5.

### Wave drag

`wave_drag_area` uses von Karman's slender-body formula in Fourier form: with
`x = L (1 - cos phi) / 2` and `S'(x) = sum A_n sin(n phi)`, `D/q = pi/4 sum n A_n^2`. The
coefficients are fitted to S(x) by least squares using the integrated basis, so S itself is
fitted and no numerical derivative is taken. The basis forces S(0) = 0 and zero slope at both
ends but allows a base area (A_1). The series is truncated at `min(30, (N - 1) / 4)` terms:
term n is weighted by n, so the truncation is what keeps tessellation noise out of the result.
A Sears-Haack body sampled on 101 stations reproduces `128 V^2 / (pi L^4)` to about 1e-5, and a
128-segment revolved Sears-Haack mesh to about 1e-3.

A nose whose second plane already has a quarter of the largest area is reported as blunt,
because the formula assumes a pointed nose.

## Tessellation

The `auto` linear deflection uses the actual STEP bounding-box diagonal, even when every model
dimension is smaller than one input unit. The value is expressed in the selected output length
unit and only the final deflection is floored at `1e-9`. Angular deflection is an angular
tolerance and is not scaled with model size.

With `--angular-deflection auto`, the angle follows the selected preset, and is `0.3` when
`--mesh-deflection` is an explicit number. `auto-fast` is accepted as an alias for `auto`.

### Speed and accuracy benchmark

Projected-area run time is roughly proportional to the triangle count. In the reference benchmark
below, the angular limit, not the linear one, set the triangle count: changing only the linear
factor from `1e-4` to `1e-3` did not change it. This is an observation for that model, not a rule
for every curved surface, but it is why the default preset mainly relaxes the angle.

Reference measurements on a synthetic 64-part curved assembly, per projection direction, against
a fine reference mesh. They describe that model and those conditions only; they are not a general
error bound:

| angular deflection | triangles | time per direction | projected-area error |
|---:|---:|---:|---:|
| `0.1` (`auto-precise`) | about 800k | about 21 s | about 0.04% |
| `0.3` (`auto`) | 100k to 160k | about 2.4 to 4 s | 0.2% to 0.4% |
| `0.5` | about 40k | about 1 s | about 1% |

The error comes from approximating curved surfaces and edges with chords, and its sign depends on
the shape and attitude. In the benchmark above, and for a convex solid such as a sphere, the chords
cut inside the outline and projected area is underestimated. Around a curved hole the chords cut
into the opening instead, so the material's projected area is overestimated: for a 10 x 10 x 1 mm
plate with a 4 mm radius through hole viewed along the hole axis, `auto-precise` reported
`+0.024%` and `auto` `+0.24%` against the exact `100 - 16π` mm².

Earlier versions used diagonal * `1e-4` and `0.1` rad for `auto`; that preset is now
`auto-precise`. On the user's own production models, the largest projected-area difference
observed between the new and the old `auto` was `0.12%`.

### STEP B-Rep vs mesh volume and surface area

Representative local comparisons of `--step-metrics mesh` against B-Rep values:

| sample | mesh deflection | volume difference | surface-area difference |
|---|---:|---:|---:|
| cube / box / frame | `auto` to coarse explicit values | about `0%` | about `0%` |
| `sphere_r1` | `D*1e-4` (`auto-precise`) | `-0.0507%` | `-0.0272%` |
| `sphere_r1` | `D*3e-5` | `-0.0153%` | `-0.0083%` |
| `sphere_r1` | `D*1e-5` | `-0.0051%` | `-0.0028%` |
| `cylinder_x_r1_l2` | `D*1e-4` (`auto-precise`) | `-0.0230%` | `-0.0115%` |
| `cylinder_x_r1_l2` | `D*3e-5` | `-0.0069%` | `-0.0034%` |
| `satellite` | `D*1e-4` (`auto-precise`) | `-0.0379%` | `-0.0148%` |
| `satellite` | `D*3e-5` | `-0.0130%` | `-0.0052%` |

## When tessellation runs

Large STEP files with curved faces can spend most of their load time in tessellation, so
cadmetrics avoids it when B-Rep values are enough. `measure` and CLI `inspect` skip STEP mesh
generation with `--step-metrics brep`; volume, surface area, base area, and coordinate bounds then
come from the B-Rep shape, and `inspect` reports `0` vertices and faces.

Mesh generation is still required for:

- `project` and `sweep`, because projected area is mesh-based
- `--step-metrics mesh`
- GUI model display
- the rare exact base-area fallback

The GUI reuses the loaded display model for `Run Sweep`, so it does not reload and tessellate the
same model again. The GUI's component preview meshes are tessellated once at load from copies of
the components, much more coarsely than the measurement mesh (about a twentieth of the triangles
on curved parts). They are never used for measurements and their time is not included in
`load_elapsed_sec`.

## Benchmarks

Projection performance can be measured reproducibly from a checkout with:

```bash
uv run python scripts/benchmark_projection.py samples/satellite/satellite.step
```

The JSON result includes mesh vertex/triangle counts, median and minimum duration, peak Python
memory observed by `tracemalloc`, and projected area. `scripts/benchmark_step_load.py` measures
STEP loading.
