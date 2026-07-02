# Accuracy Notes

cadmetrics combines exact CAD-kernel calculations and mesh-based projected-area calculations.
Understanding the difference is important when comparing results with CAD software.

## Geometry Backends

STL files are mesh geometry. Volume, surface area, and projected area are calculated from the
mesh. Self-intersecting or overlapping STL components are not repaired automatically; in those
cases volume and surface area can double-count overlaps or otherwise become unreliable.

STEP files use the optional `step` extra:

```bash
pip install "cadmetrics[step]"
```

For STEP input:

- volume uses OCP/OpenCascade `VolumePropertiesGK` after boolean-unioning multiple solids
- surface area uses the OCP/OpenCascade B-Rep model after boolean-unioning multiple solids
- projected area uses a tessellated mesh generated from the B-Rep

OCP does not expose a separate `SurfacePropertiesGK` function. Surface area uses
`SurfaceProperties`; OCP's Python binding also exposes an adaptive-integration overload that
accepts an error tolerance, but cadmetrics currently keeps the default exact-surface call.

## STEP B-Rep vs STL-Like Mesh Values

It is possible to tessellate a STEP model and then calculate volume and surface area from the
triangle mesh, as if the model had been converted to STL. cadmetrics keeps B-Rep volume and
surface area as the default for STEP because those values avoid tessellation error.

The mesh-based values are useful for debugging STL comparisons, but they are approximations.
Planar solids usually match exactly because their faces can be represented by triangles without
geometric approximation. Curved solids depend on `--mesh-deflection` and
`--angular-deflection`.

Representative local comparisons against B-Rep values:

| sample | mesh deflection | volume difference | surface-area difference |
|---|---:|---:|---:|
| cube / box / frame | `auto` to `0.01` | about `0%` | about `0%` |
| `sphere_r1` | `auto` | `-0.0051%` | `-0.0028%` |
| `sphere_r1` | `0.001` | `-0.144%` | `-0.077%` |
| `cylinder_x_r1_l2` | `auto` | `-0.0023%` | `-0.0012%` |
| `cylinder_x_r1_l2` | `0.001` | `-0.041%` | `-0.021%` |
| `satellite` | `auto` | `-0.0047%` | `-0.0017%` |
| `satellite` | `0.001` | `-0.0415%` | `-0.0157%` |

For intersecting STEP solids, tessellate after the STEP boolean union if mesh-based comparison
is needed. Tessellating or exporting components independently and then summing STL metrics can
double-count overlap volume and area.

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
auto = STEP bounding-box diagonal * 1e-5
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

Use the default settings for quick sweeps. Tighten `--mesh-deflection` when:

- validating against CAD software
- evaluating small curved features
- comparing close projected-area differences

Keep the deflection fixed when comparing many versions of similar geometry.
