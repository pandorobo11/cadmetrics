# Accuracy Notes

cadmetrics combines exact CAD-kernel calculations and mesh-based projected-area calculations.
Understanding the difference is important when comparing results with CAD software.

## Geometry Backends

STL files are mesh geometry. Volume, surface area, and projected area are calculated from the
mesh. Self-intersecting or overlapping STL components are not repaired automatically; in those
cases volume and surface area can double-count overlaps or otherwise become unreliable.
When multiple STL files are passed in one command, their meshes are concatenated into one
calculation model with the same limitation.

STEP files use the optional `step` extra:

```bash
pip install "cadmetrics[step]"
```

For STEP input:

- volume uses OCP/OpenCascade `VolumePropertiesGK` after boolean-unioning multiple solids
- surface area uses the OCP/OpenCascade B-Rep model after boolean-unioning multiple solids
- `--step-metrics mesh` can instead calculate STEP volume and surface area from the
  tessellated mesh after boolean union
- projected area uses a tessellated mesh generated from the B-Rep
- the GUI can exclude selected STEP solid components before boolean union and measurement

When multiple STEP files are passed in one command, cadmetrics loads their solids into one
compound and applies the same boolean-union step before measurement. STEP and STL files cannot
be mixed in one calculation model.

OCP does not expose a separate `SurfacePropertiesGK` function. Surface area uses
`SurfaceProperties`; OCP's Python binding also exposes an adaptive-integration overload that
accepts an error tolerance, but cadmetrics currently keeps the default exact-surface call.

## STEP B-Rep vs STL-Like Mesh Values

It is possible to tessellate a STEP model and then calculate volume and surface area from the
triangle mesh, as if the model had been converted to STL. Use `--step-metrics mesh` for this
mode. cadmetrics keeps B-Rep volume and surface area as the default for STEP because those
values avoid tessellation error.

The mesh-based values are useful for debugging STL comparisons, but they are approximations.
Planar solids usually match exactly because their faces can be represented by triangles without
geometric approximation. Curved solids depend on `--mesh-deflection` and
`--angular-deflection`.

Representative local comparisons against B-Rep values:

| sample | mesh deflection | volume difference | surface-area difference |
|---|---:|---:|---:|
| cube / box / frame | `auto` to coarse explicit values | about `0%` | about `0%` |
| `sphere_r1` | `D*1e-4` current `auto` | `-0.0507%` | `-0.0272%` |
| `sphere_r1` | `D*3e-5` | `-0.0153%` | `-0.0083%` |
| `sphere_r1` | `D*1e-5` | `-0.0051%` | `-0.0028%` |
| `cylinder_x_r1_l2` | `D*1e-4` current `auto` | `-0.0230%` | `-0.0115%` |
| `cylinder_x_r1_l2` | `D*3e-5` | `-0.0069%` | `-0.0034%` |
| `satellite` | `D*1e-4` current `auto` | `-0.0379%` | `-0.0148%` |
| `satellite` | `D*3e-5` | `-0.0130%` | `-0.0052%` |

For intersecting STEP solids, tessellate after the STEP boolean union if mesh-based comparison
is needed. Tessellating or exporting components independently and then summing STL metrics can
double-count overlap volume and area.

## Multi-Component STEP Files

cadmetrics treats multiple STEP solids as one geometric model by default. The selected solids
are boolean-unioned before B-Rep volume and surface-area measurement, so intersections between
enabled solids are not double-counted when the union succeeds.

The GUI's component filters operate before that union step. Turning off a component removes it
from display, volume, surface-area, and projected-area calculations. Component labels use
STEP/XCAF names when available and otherwise fall back to solid order in the loaded STEP file.
Full assembly hierarchy is not preserved yet.

The same geometry rule applies to multi-file STEP input. Each STEP file contributes its detected
solids to one combined model. With `--unit auto`, all detected STEP units must match; otherwise,
specify a common `--unit` explicitly after confirming the files use the same source unit.

## Projected Area Definition

Projected area is the orthographic 2D outline area for the selected projection direction.
Overlapping projected regions are counted once.

This is intended for aerodynamic projected-area and drag-area screening, where the silhouette
area matters more than the sum of all visible facets.

## Tessellation Controls

STEP projected area depends on tessellation. The most important control is:

```bash
--mesh-deflection
```

The default is:

```text
auto = STEP bounding-box diagonal * 1e-4
```

The value is expressed in the selected output length unit. Smaller values usually improve
projected-area accuracy for curved geometry but increase calculation time.

For reproducible validation runs, pass an explicit value:

```bash
cadmetrics project model.step --mesh-deflection 0.001
```

`--angular-deflection` defaults to `0.1`. It is an angular tolerance, so cadmetrics does not
scale it with model size.

## Watertightness

Open or non-watertight STL meshes are accepted with warnings. Surface area and projected area
can still be useful, but volume may be unreliable or unavailable.

STEP surface-only geometry may load if tessellation succeeds. In that case, volume may be zero
or unavailable.

## Validation Target

The current target is within `0.1%` against Fusion 360 for representative closed solids.

The satellite sample has been manually checked against Fusion 360:

- volume and surface area match Fusion's rounded physical properties
- projected-area sweep values match Fusion's rounded displayed values

See [Fusion 360 Validation Notes](fusion_validation.md) for details.

## Practical Guidance

Use the default settings for normal sweeps. Tighten `--mesh-deflection` when:

- validating against CAD software
- evaluating small curved features
- comparing close projected-area differences

Typical settings:

| use case | `--mesh-deflection` | `--angular-deflection` |
|---|---:|---:|
| Fast preview | bounding-box diagonal * `1e-3` | `0.3` to `0.5` |
| Normal projected-area work | bounding-box diagonal * `1e-4` | `0.1` |
| CAD comparison / final validation | bounding-box diagonal * `3e-5` to `1e-5` | `0.05` to `0.1` |

Keep the deflection fixed when comparing many versions of similar geometry.
