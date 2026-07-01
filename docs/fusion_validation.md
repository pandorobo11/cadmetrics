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

## 2026-07-01: Satellite Projected-Area Sweep

The same satellite model was checked in Fusion 360 for `alpha=0..90 deg` in `15 deg`
increments.

Fusion 360 displays area values rounded in scientific notation in the status bar. The
cadmetrics values below were calculated with:

```bash
uv run cadmetrics sweep samples/satellite/satellite.step \
  --output-unit mm \
  --attitude alpha-beta \
  --alpha 0:90:15 \
  --beta 0 \
  --no-summary
```

| cadmetrics alpha | Fusion 360 display | cadmetrics |
|---:|---:|---:|
| `0 deg` | `7.854E+05 mm^2` | `785,372.351552 mm^2` |
| `15 deg` | `1.535E+06 mm^2` | `1,535,047.379169 mm^2` |
| `30 deg` | `2.234E+06 mm^2` | `2,234,197.015840 mm^2` |
| `45 deg` | `2.800E+06 mm^2` | `2,800,196.784857 mm^2` |
| `60 deg` | `3.180E+06 mm^2` | `3,179,890.524209 mm^2` |
| `75 deg` | `3.345E+06 mm^2` | `3,345,124.905654 mm^2` |
| `90 deg` | `3.284E+06 mm^2` | `3,283,992.455144 mm^2` |

Conclusion: the manual Fusion 360 sweep agrees with cadmetrics within Fusion's rounded
display precision for all checked attitudes.
