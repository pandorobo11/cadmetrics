# Sample Geometry

The `samples/` directory contains deterministic CAD fixtures for validating volume,
surface-area, and projected-area behavior.

Regenerate all sample files with:

```bash
uv run python scripts/generate_samples.py
```

Most samples include:

- STEP: exact B-Rep source for STEP loading checks
- ASCII STL: text STL mesh loading checks
- Binary STL: binary STL mesh loading checks

`open_cube_missing_face` intentionally has no STEP file because it is a non-watertight STL
fixture for warning behavior.

STEP files declare millimeter units. Analytic STEP samples are generated at 1000x their
meter dimensions so `cadmetrics` with default `--unit auto --output-unit m` reports the same
meter-based expected values as the STL fixtures.

## Shapes

| name | purpose | key expected values |
|---|---|---|
| `unit_cube` | simplest closed solid | volume `1`, surface `6`, +X projection `1` |
| `box_1x2x3` | direction and attitude sanity check | volume `6`, surface `22`, +X projection `6` |
| `sphere_r1` | attitude-invariant reference | volume `4/3*pi`, surface `4*pi`, projection `pi` |
| `cylinder_x_r1_l2` | axis-sensitive curved shape | volume `2*pi`, surface `6*pi`, +X projection `pi` |
| `two_boxes_overlap_projection` | projected-overlap removal | volume `2`, surface `12`, +X projection `1` |
| `two_boxes_intersecting` | STEP boolean-union vs raw STL overlap behavior | STEP volume `1.5`, STEP surface `8`, STL volume `2`, STL surface `12`, +X projection `1` |
| `open_cube_missing_face` | non-watertight STL warning | surface `5`, +X projection `1`, `is_watertight=false` |
| `frame_with_hole` | hole and concave outline behavior | volume `0.8`, surface `17.6`, +Z projection `8` |
| `satellite` | manually added Fusion 360 validation model | see [Fusion validation notes](fusion_validation.md) |

The authoritative machine-readable list is [samples/metadata.json](../samples/metadata.json).
