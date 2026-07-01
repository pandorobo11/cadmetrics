# Fusion 360 Validation Notes

## 2026-06-27: `samples/satellite/satellite.step`

Manual validation was performed against Autodesk Fusion 360 using the manually added
`samples/satellite/satellite.step` model.

### Physical Properties

Fusion 360 displayed rounded physical properties in millimeter units:

| property | Fusion 360 display | cadmetrics |
|---|---:|---:|
| volume | about `2.561E+09 mm^3` | `2,561,328,923.008496 mm^3` |
| surface area | about `1.168E+07 mm^2` | `11,680,313.693154 mm^2` |
| bounding box X | `3309.76 mm` | `3309.760217 mm` |
| bounding box Y | `1000 mm` | `1000.000000 mm` |
| bounding box Z | `1000 mm` | `999.999778 mm` |

cadmetrics command:

```bash
uv run cadmetrics measure samples/satellite/satellite.step --output-unit mm
```

### Projected Area

Fusion 360 measured the area of a projected/intersection sketch on a plane inclined by
`30 deg` and displayed:

```text
3.180E+06 mm^2
```

This corresponds to `alpha=60 deg` in cadmetrics, because the Fusion plane angle is the
plane inclination and cadmetrics `alpha` describes the projection direction. The projection
direction is normal to the plane, so the angle is complementary in this setup.

cadmetrics commands:

```bash
uv run cadmetrics project samples/satellite/satellite.step --output-unit mm --alpha 30
uv run cadmetrics project samples/satellite/satellite.step --output-unit mm --alpha 60
uv run cadmetrics project samples/satellite/satellite.step --output-unit mm --attitude vector --direction 0.5,0,0.8660254
```

Results:

| case | projected area |
|---|---:|
| Fusion 360, plane inclined by `30 deg` | `3.180E+06 mm^2` |
| cadmetrics `alpha=30 deg` | `2,234,250.858218 mm^2` |
| cadmetrics `alpha=60 deg` | `3,179,941.201566 mm^2` |
| cadmetrics `direction=0.5,0,0.8660254` | `3,179,941.201566 mm^2` |

Difference between Fusion's displayed value and cadmetrics `alpha=60 deg` is approximately
`58.8 mm^2`, or about `0.0019%` relative to the rounded Fusion value.

Conclusion: the Fusion 360 inclined-plane measurement is consistent with cadmetrics
`alpha=60 deg`, not `alpha=30 deg`.
