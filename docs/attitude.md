# Attitude Angles

This page defines the angles cadmetrics uses to describe the projection direction: the direction
you look along when measuring projected area.

## Coordinate system

```text
X: aft (toward the rear)
Y: right
Z: up
```

If your model uses other axes, set the axis map first (see
[Coordinate system](concepts.md#coordinate-system)).

The projection direction is written as a vector of length 1:

```text
d = (d_x, d_y, d_z)
```

Projected area is the silhouette area seen when looking along `d`. Looking along `d` and along
`-d` gives the same projected area.

The angles describe the direction you look from. They do not rotate the model.

## Three ways to give the direction

| mode | GUI | CLI / Python | sweep |
|---|---|---|---|
| Alpha / Beta | `Alpha / Beta` | `alpha-beta` | yes |
| Roll / Pitch | `Roll / Pitch` | `roll-pitch` | yes |
| Unit vector | `Unit vector` | `vector` | no, one direction only |

Each mode uses only its own inputs; there is no hidden extra rotation.

## Alpha and Beta

`alpha` is the angle of attack and `beta` is the sideslip angle, in degrees:

```text
d = (cos(alpha) cos(beta), -sin(beta), sin(alpha) cos(beta))
```

| input | direction |
|---|---|
| `alpha=0`, `beta=0` | `(1, 0, 0)`: from the front |
| `alpha=90`, `beta=0` | `(0, 0, 1)`: from below, looking up |
| `alpha=0`, `beta=90` | `(0, -1, 0)`: from the right side |

## Roll and Pitch

`pitch` is how far the direction tilts away from +X. `roll` is the angle around the X axis that
decides which way it tilts. Positive roll turns from +Z toward −Y (a right-hand rotation about
+X).

Think of a cone around +X: `pitch` sets how wide the cone is, and `roll` sets where on the cone
the direction lies.

| input | direction |
|---|---|
| `roll=0`, `pitch=0` | `(1, 0, 0)`: from the front |
| `roll=0`, `pitch=90` | `(0, 0, 1)` |
| `roll=90`, `pitch=90` | `(0, -1, 0)` |

## Unit vector

Give the direction directly as `x, y, z`. The vector does not need to have length 1: cadmetrics
scales it for you. It cannot be `(0, 0, 0)`.

## How results report the direction

Every result row reports the direction in all three forms: `alpha_deg`/`beta_deg`,
`roll_deg`/`pitch_deg`, and `direction_x/y/z`. The `attitude` column tells you which mode you
used.

- The angles of the mode you used are kept exactly as you entered them. For example, alpha 360
  stays 360.
- The other angles are calculated back from the direction, so they fall in fixed ranges: `alpha`
  −180 to 180, `beta` −90 to 90, `pitch` 0 to 180.
- In `vector` mode, both angle pairs are calculated from the direction.

The formulas used to calculate angles from a direction are:

```text
alpha = atan2(d_z, d_x)
beta  = asin(-d_y)
pitch = atan2(sqrt(d_y^2 + d_z^2), d_x)
roll  = atan2(-d_y, d_z)
```

## Examples

```bash
cadmetrics project model.step --attitude alpha-beta --alpha 10 --beta 0
cadmetrics project model.step --attitude roll-pitch --roll 0 --pitch 10
cadmetrics project model.step --attitude vector --direction 1,0,0
cadmetrics sweep model.step --attitude alpha-beta --alpha -5:5:5 --beta -2:2:2
```

```python
from cadmetrics import project

project("model.step", attitude="alpha-beta", alpha_deg=10, beta_deg=0)
project("model.step", attitude="roll-pitch", roll_deg=0, pitch_deg=10)
project("model.step", attitude="vector", direction="1,0,0")
```
