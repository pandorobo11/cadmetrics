# Sample Models

The `samples/` folder of the cadmetrics source repository contains small test models with known answers. Use them to try cadmetrics or to check that it
works as expected on your computer. They are not installed with `pip`.

Most samples come as a STEP file, an ASCII STL file, and a binary STL file. The values below are
in meters, which is what you get with the default settings.

| name | what it shows | expected values |
|---|---|---|
| `unit_cube` | the simplest closed solid | volume `1`, surface `6`, base `1`, projection from +X `1` |
| `box_1x2x3` | that directions and axes are right | volume `6`, surface `22`, base `6`, projection from +X `6` |
| `sphere_r1` | a shape that looks the same from every direction | volume `4/3·π`, surface `4·π`, base `0`, projection `π` |
| `cylinder_x_r1_l2` | a curved shape that depends on direction | volume `2·π`, surface `6·π`, base `π`, projection from +X `π` |
| `two_boxes_overlap_projection` | overlapping silhouettes are counted once | volume `2`, surface `12`, projection from +X `1` |
| `two_boxes_intersecting` | STEP merges overlapping solids; STL does not | STEP volume `1.5`, surface `8`; STL volume `2`, surface `12`; projection from +X `1` |
| `multi_file_step_components` | choosing components across two STEP files | all components: volume `4`, surface `24`; components 2 and 3: volume `2`, surface `12` |
| `open_cube_missing_face` | an STL with a hole, which has no volume | surface `5`, projection from +X `1`, not watertight |
| `frame_with_hole` | a hole and a concave outline | volume `0.8`, surface `17.6`, projection from +Z `8` |
| `satellite` | a realistic model checked against Fusion 360 | volume about `2.561` m³ (`2.561E+09` mm³) |

Notes:

- `open_cube_missing_face` has no STEP file, because it exists to show the "not watertight"
  warning for STL.
- `multi_file_step_components` has no STL file. Open `box_pair_a.step` and `box_pair_b.step`
  together.
- The STEP samples are stored in millimeters; with `Input unit` `auto` they give the same meter
  values as the STL files.

Try one from the command line:

```bash
cadmetrics measure samples/unit_cube/unit_cube.step
cadmetrics project samples/box_1x2x3/box_1x2x3.step --alpha 0
```

The full list of expected values is in [samples/metadata.json](../samples/metadata.json).
