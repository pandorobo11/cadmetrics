# Attitude Definition

cadmetrics describes projected area by the direction of orthographic projection.

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

If the source CAD axes do not match this convention, apply an axis map before calculating
attitudes. For example, `x,-z,y` means:

```text
cadmetrics X = input X
cadmetrics Y = input -Z
cadmetrics Z = input Y
```

The CLI option is `--axis-map`; the GUI exposes the same setting as `Axis map` in `Setup`.

## Input Modes

The CLI and GUI expose three input modes:

| mode | meaning | sweep support |
|---|---|---|
| `alpha-beta` | angle of attack and sideslip | yes |
| `roll-pitch` | azimuth around +X and pitch away from +X | yes |
| `vector` | explicit projection direction vector | no, one direction only |

The output CSV always reports all equivalent representations:

- `alpha_deg`, `beta_deg`
- `roll_deg`, `pitch_deg`
- `direction_x`, `direction_y`, `direction_z`

The `attitude` column names the input mode. That mode's own angle pair keeps the requested values
exactly as given, without normalization: an `alpha-beta` sweep reports `alpha_deg=360` for alpha
360, and its `beta_deg=-90` rows keep their requested alpha values even though they share one
direction. The other mode's pair and the direction vector are recovered from the projection
direction with the formulas below, so they are normalized (`alpha` in -180..180, `beta` in
-90..90, `pitch` in 0..180). In `vector` mode, both angle pairs are recovered.

## Alpha and Beta

In `alpha-beta` mode, cadmetrics builds the projection direction from angle of attack and
sideslip:

```text
d = (cos(alpha) cos(beta), -sin(beta), sin(alpha) cos(beta))
```

When alpha/beta are not the input mode, they are recovered from a unit vector as:

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

In `roll-pitch` mode, `pitch` is the angle away from the +X direction. Positive `roll` is the
right-hand rotation around the +X axis, measured from +Z toward -Y.

When roll/pitch are not the input mode, they are recovered as:

```text
pitch = atan2(sqrt(d_y^2 + d_z^2), d_x)
roll  = atan2(-d_y, d_z)
```

This representation is useful when thinking of a direction cone from +X and a roll angle around
that cone using the aircraft-style positive direction.

## Unit Vector

For explicit vector input:

```bash
cadmetrics project model.step --attitude vector --direction 1,0,0
```

cadmetrics normalizes the vector first, then recovers equivalent `alpha`/`beta` and
`roll`/`pitch` values for CSV and GUI display.

## CLI Examples

Single projected-area calculations:

```bash
cadmetrics project model.step --attitude alpha-beta --alpha 10 --beta 0
cadmetrics project model.step --attitude roll-pitch --roll 0 --pitch 10
cadmetrics project model.step --attitude vector --direction 1,0,0
```

For convenience, `--attitude` can be omitted:

- `--direction` implies `vector`
- `--pitch` implies `roll-pitch`
- otherwise cadmetrics uses `alpha-beta`

## Sweep Behavior

For `alpha-beta`, the CLI sweep command accepts `alpha` and `beta` ranges:

```bash
cadmetrics sweep model.step --attitude alpha-beta --alpha -5:5:5 --beta -2:2:2
```

For `roll-pitch`, it accepts `roll` and `pitch` ranges:

```bash
cadmetrics sweep model.step --attitude roll-pitch --roll 0:20:10 --pitch 0:10:5
```

For `vector`, the CLI accepts one explicit direction and returns one row:

```bash
cadmetrics sweep model.step --attitude vector --direction 1,0,0
```

The calculation evaluates every combination of the selected angle ranges. There is no hidden
extra rotation order in the CLI modes: `alpha-beta` uses only alpha/beta, `roll-pitch` uses only
roll/pitch, and `vector` uses only the normalized direction vector.
