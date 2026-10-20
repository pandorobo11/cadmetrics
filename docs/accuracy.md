# Accuracy and Mesh Settings

This page explains how accurate cadmetrics results are and which settings change them.

## Short version

- For STEP files, **volume, surface area, and base area** are calculated from the exact CAD
  geometry. Mesh settings do not change them.
- **Projected area** is always calculated from a triangle mesh, so it carries a small error that
  depends on how fine the mesh is.
- The default mesh setting (`auto`, GUI `Fast`) is meant for quickly exploring many directions.
  Its projected-area error is usually a few tenths of a percent or less.
- For final numbers, rerun the directions that matter with `auto-precise` (GUI `Precise`).
- **STL** results are always mesh-based, and depend on how the STL file was exported.

## Why projected area depends on the mesh

To calculate the silhouette, cadmetrics turns curved CAD surfaces into many small flat triangles
(a mesh). Flat triangles cannot follow a curve exactly, so the outline of a curved part comes out
very slightly different from the true shape. Finer meshes are closer to the true shape but take
longer to calculate.

The error can go either way. For a convex shape such as a sphere, the mesh sits slightly inside the
true outline, so projected area comes out a little low. Around a round hole the mesh cuts into the
hole, so the area comes out a little high. A coarse mesh is therefore not a safe upper or lower
limit.

Flat-faced shapes, such as boxes, have no mesh error.

## Mesh settings

These settings only apply to STEP files.

| CLI `--mesh-deflection` | GUI `Mesh quality` | use it for |
|---|---|---|
| `auto` (default) | `Fast (default)` | exploring many directions quickly |
| `auto-precise` | `Precise` | final numbers, comparisons with CAD software |
| a number | `Mesh deflection` with `Auto` unchecked | full control, reproducible validation |

`auto` and `auto-precise` scale the mesh to the size of the model, so they work for small and
large models alike.

On a test model with many curved parts, `auto` was about 5 to 9 times faster than `auto-precise`,
with a projected-area error of 0.2% to 0.4% (about 0.04% with `auto-precise`). These numbers are
for that model only; your results will differ with the shape.

There are two fine-tuning options:

- **Mesh deflection** (`--mesh-deflection`): the largest gap allowed between the true surface and
  the mesh, in the output unit. Smaller is finer.
- **Angular deflection** (`--angular-deflection`): the largest angle allowed between neighboring
  triangles, in radians. Smaller is finer. With `auto`, it is `0.3` (or `0.1` with
  `auto-precise`). This setting usually has the bigger effect on speed.

The values actually used are saved in the `mesh_deflection` and `angular_deflection` columns of
every result.

| use case | `--mesh-deflection` | `--angular-deflection` |
|---|---|---|
| Quick preview | `auto` | `auto` (`0.3`) to `0.5` |
| Precise projected area | `auto-precise` | `auto` (`0.1`) |
| Comparison with CAD software | model size × `3e-5` to `1e-5` | `0.05` to `0.1` |

Here, "model size" is the length of the diagonal of the model's bounding box.

Keep the settings the same when you compare several versions of a design, so that differences in
the results come from the design and not from the mesh.

### Changed default in recent versions

In earlier versions, `auto` meant what is now called `auto-precise`. If you compare results with
those versions, projected areas with default settings can differ slightly (up to 0.12% on the
production models that were checked). Use `auto-precise` to reproduce the earlier results.

## What the mesh affects

| value | depends on mesh settings? |
|---|---|
| Projected area and centroid | yes |
| 3D view in the GUI | yes |
| STEP volume and surface area | no (yes with `--step-metrics mesh` / `STEP metrics` `Mesh`) |
| STEP base area | no (except in rare cases where cadmetrics falls back to the mesh, with a warning) |
| STL values | no; the STL triangles are used as they are |

## Comparing STEP with STL

An STL file is itself a mesh made when it was exported, so its volume and surface area are
slightly different from the exact STEP values, especially for curved shapes. If you want STEP
results that behave like STL results, set `--step-metrics mesh` (GUI: `STEP metrics` > `Mesh`).
For curved shapes the difference is typically a few hundredths of a percent with `auto-precise`.

If parts overlap, compare against a STEP model that was merged before export. Exporting parts to
separate STL files and adding their values counts the overlaps twice.

## Several solids and overlaps

When a STEP model has several solids, cadmetrics merges them into one before measuring, so
overlapping volume and surface are counted only once. In rare cases the merge fails. cadmetrics
then measures the solids without merging and adds the warning `Could not boolean-union`: volume and
surface area may count overlaps twice. Projected area is not affected. In `Subtract unchecked`
mode, a failed merge stops loading with an error instead.

STL files are never merged, so overlapping STL parts always count their overlap twice in volume and
surface area.

## Base area

Base area is the area of the flat faces at the very rear of the model (the largest X). A shape
that only touches its rearmost point with a curve, such as a sphere, has no base face, so its base
area is `0` with a warning.

`Base tolerance` (`--base-tolerance`) decides how close to the rear end a face must be to count.
The default rarely needs changing. Increase it a little for slightly uneven meshes exported from
other tools; decrease it if nearby faces that are not really at the rear end are being counted.

## Validation

cadmetrics aims to agree within 0.1% with Fusion 360 for typical closed solids, using
`auto-precise` for projected area. The `satellite` sample was checked by hand: its volume, surface
area, and projected areas from 0° to 90° all match Fusion 360's displayed values.
