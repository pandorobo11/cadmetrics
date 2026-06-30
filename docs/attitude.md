# Attitude Definition

cadmetrics describes projected area by the direction of orthographic projection, not by the
inclination of a measurement plane.

The default model coordinate convention is:

```text
X aft
Y right
Z up
```

The projection direction is represented as a normalized vector in model coordinates:

```text
d = (d_x, d_y, d_z)
```

Projected area is the 2D outline area seen when looking along `d`.

## Alpha and Beta

For `alpha` and `beta` input, cadmetrics uses an aircraft-style projection-direction convention
with roll fixed to zero:

```text
d = (cos(alpha) cos(beta), -sin(beta), sin(alpha) cos(beta))
```

The equivalent output angles are recovered from a unit vector as:

```text
alpha = atan2(d_z, d_x)
beta  = asin(-d_y)
```

Examples:

| input | direction |
|---|---|
| `alpha=0`, `beta=0` | `(1, 0, 0)` |
| `alpha=90`, `beta=0` | `(0, 0, 1)` |
| `alpha=0`, `beta=90` | `(0, -1, 0)` |

## Roll and Pitch

The GUI also supports `roll` and `pitch` input. `pitch` is the angle away from the +X direction.
`roll` is the azimuth around +X, measured from +Z toward +Y.

The equivalent output values are:

```text
pitch = atan2(sqrt(d_y^2 + d_z^2), d_x)
roll  = atan2(d_y, d_z)
```

This representation is useful when thinking of a direction cone from +X and a rotation around
that cone.

## Unit Vector

For explicit vector input:

```bash
cadmetrics project model.step --direction 1,0,0
```

cadmetrics normalizes the vector first, then calculates equivalent `alpha`/`beta` and
`roll`/`pitch` values for CSV and GUI display.

## Sweep Order

The CLI sweep command accepts `roll`, `alpha`, and `beta` ranges:

```bash
cadmetrics sweep model.step --roll 0:20:10 --alpha -5:5:5 --beta -2:2:2
```

The calculation evaluates every combination of those ranges. Conceptually, the aircraft-style
attitude order is:

```text
roll -> alpha -> beta
```

## Fusion 360 Plane Angles

Fusion 360 often reports or constructs the angle of a sketch or measurement plane. cadmetrics
uses the projection direction, which is normal to that plane. Because of that, a plane angle and
a cadmetrics projection angle can be complementary.

For example, a Fusion 360 plane inclined by `30 deg` can correspond to a cadmetrics projection
direction of `alpha=60 deg`, depending on how the plane was constructed.

When comparing with CAD tools, `--direction x,y,z` is the least ambiguous input.

See [Fusion 360 validation notes](fusion_validation.md) for the satellite sample comparison.
