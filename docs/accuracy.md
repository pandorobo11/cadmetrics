# Accuracy Notes

cadmetrics combines exact CAD-kernel calculations and mesh-based projected-area calculations.
Understanding the difference is important when comparing results with CAD software.

## Geometry Backends

STL files are mesh geometry. Volume, surface area, and projected area are calculated from the
mesh.

STEP files use the optional `step` extra:

```bash
pip install "cadmetrics[step]"
```

For STEP input:

- volume uses the OCP/OpenCascade B-Rep model
- surface area uses the OCP/OpenCascade B-Rep model
- projected area uses a tessellated mesh generated from the B-Rep

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
- a Fusion plane inclined by `30 deg` matches cadmetrics `alpha=60 deg`
- the projected-area difference is about `0.0019%` relative to Fusion's rounded displayed value

See [Fusion 360 Validation Notes](fusion_validation.md) for details.

## Practical Guidance

Use the default settings for quick sweeps. Tighten `--mesh-deflection` when:

- validating against CAD software
- evaluating small curved features
- comparing close projected-area differences

Keep the deflection fixed when comparing many versions of similar geometry.
