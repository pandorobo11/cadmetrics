# Using the CLI

The `cadmetrics` command runs calculations from a terminal. It is handy for scripts and batch
jobs, and gives the same results as the GUI.

## Commands

| command | what it does |
|---|---|
| `cadmetrics measure` | volume, surface area, base area, and bounds |
| `cadmetrics project` | projected area for one direction |
| `cadmetrics sweep` | projected area for a range of angles |
| `cadmetrics sections` | cross-sectional area distribution along X, for the area rule |
| `cadmetrics inspect` | information about the model, such as its unit and components |
| `cadmetrics samples` | the bundled sample models |

Run `cadmetrics COMMAND --help` to see every option of a command.

STL files work with the base package (`pip install cadmetrics`). STEP files need
`pip install "cadmetrics[step]"`.

## Output: terminal or CSV

`measure` and `project` print a readable table in the terminal. Add `--out FILE.csv` (or
`-o FILE.csv`) to save the results as CSV instead:

```bash
cadmetrics measure model.step --out measure.csv
```

`sweep` prints a progress bar while it runs. Without `--out`, it writes the CSV rows to the
terminal, so you can also redirect them with `> sweep.csv`. After a sweep, a short summary of the
smallest, largest, and average projected area is printed; add `--no-summary` to turn it off.

`measure`, `project`, and `sweep` write the same CSV columns. See [Result Columns](results.md).
`sections` writes its own columns, one row per cutting plane; see
[Cross Sections and the Area Rule](sections.md#result-columns).
`inspect` and `samples` print information only and do not have a CSV output option.

## measure

Calculate volume, surface area, base area, and bounds:

```bash
cadmetrics measure model.step
```

Report the results in millimeters:

```bash
cadmetrics measure model.step --output-unit mm
```

## project

Calculate the projected area for one direction. Choose the attitude mode with `--attitude`:

| `--attitude` | options |
|---|---|
| `alpha-beta` | `--alpha`, `--beta` |
| `roll-pitch` | `--roll`, `--pitch` |
| `vector` | `--direction x,y,z` |

```bash
cadmetrics project model.step --attitude alpha-beta --alpha 10 --beta 0
cadmetrics project model.step --attitude roll-pitch --roll 0 --pitch 10
cadmetrics project model.step --attitude vector --direction 1,0,0
```

Angles are in degrees and default to 0. The direction vector does not need to have length 1;
cadmetrics scales it for you. Options from another mode cannot be mixed in, for example `--roll`
with `--attitude alpha-beta`.

You can leave out `--attitude`: `--direction` selects `vector`, `--pitch` selects `roll-pitch`,
and otherwise `alpha-beta` is used.

See [Attitude Angles](attitude.md) for what each angle means.

## sweep

Calculate projected area for every combination of two angle ranges. Write a range as
`start:end:step`:

```bash
cadmetrics sweep model.step \
  --attitude alpha-beta \
  --alpha -10:20:1 \
  --beta -5:5:1 \
  --out sweep.csv
```

```bash
cadmetrics sweep model.step \
  --attitude roll-pitch \
  --roll 0:180:10 \
  --pitch 0:90:5 \
  --out sweep.csv
```

- `end` is included when the steps land on it exactly; `0:90:5` gives 0, 5, …, 90.
- A single number is also allowed, for example `--beta 0`.
- To count down, use a negative step, for example `90:0:-15`.
- One sweep can have at most 10,000 combinations.

With `--attitude vector`, `sweep` calculates the one given direction and returns one row.

## sections

Calculate the cross-sectional area distribution along X. Like `sweep`, it shows a progress bar,
writes CSV rows to the terminal unless `--out` is given, and then prints a summary with the
largest area, the wave drag D/q, and the matching Sears-Haack D/q (`--no-summary` turns it off).

```bash
cadmetrics sections model.step --sections 101 --out sections.csv
```

```bash
cadmetrics sections model.step --mach 1.6 --thetas 16 --symmetric --out sections.csv
```

- `--sections`: number of cutting planes from the front to the rear, 5 to 2001 (default 101).
- `--mach`: 1 (default) cuts planes normal to X; above 1 cuts Mach planes.
- `--thetas`: number of roll angles for Mach planes (default 16).
- `--symmetric`: the model is mirror-symmetric about the XZ plane; cut about half the roll
  angles. `--thetas` must be even.

See [Cross Sections and the Area Rule](sections.md) for what the values mean.

## inspect

Check a model before calculating:

```bash
cadmetrics inspect model.step
```

`inspect` prints the detected unit, bounds, volume, surface area, whether the shape is closed
(watertight), warnings, and, for STEP files, the numbered list of components. For STEP files the
vertex and face counts can show `0`, because `inspect` skips building a mesh to save time.

## samples

List the sample models that come with cadmetrics, or print the folder they are in:

```bash
cadmetrics samples
cadmetrics samples --path
```

Use the folder path to try a command on a sample:

```bash
cadmetrics measure "$(cadmetrics samples --path)/satellite/satellite.step" --output-unit mm
```

See [Sample Models](samples.md) for what each sample shows and its expected values.

## Several files

`measure`, `project`, `sweep`, and `inspect` accept more than one file and treat them as one model:

```bash
cadmetrics project fuselage.step wing.step tail.step --alpha 10
```

All files must be the same format. See
[Several files as one model](concepts.md#several-files-as-one-model).

## STEP components

Use `inspect` to see the component numbers, then pick components with `--step-component`. Repeat
it for each component you want to keep:

```bash
cadmetrics measure assembly.step --step-component 1 --step-component 3
```

Add `--component-mode subtract` to cut the other components away from the selected ones instead
of leaving them out:

```bash
cadmetrics measure assembly.step \
  --step-component 1 --step-component 3 \
  --component-mode subtract
```

See [STEP components](concepts.md#step-components).

## Options

These options work with `measure`, `project`, `sweep`, and `inspect`, except where noted.
They do not apply to `samples`, which only provides `--path` (and `--help`).

| option | default | meaning |
|---|---|---|
| `--unit` | `auto` | Length unit of the model file. `auto` reads it from STEP files and uses `m` for STL. |
| `--output-unit` | `m` | Unit for all results: `m`, `mm`, `cm`, `in`, or `ft`. |
| `--axis-map` | `x,y,z` | Which of your model's axes become cadmetrics X, Y, Z, for example `x,-z,y`. See [Coordinate system](concepts.md#coordinate-system). |
| `--step-component` | all | 1-based STEP component to include. Repeat for several. |
| `--component-mode` | `filter` | `filter` leaves unselected components out; `subtract` cuts them away. |
| `--step-metrics` | `brep` | Source of STEP volume and surface area: `brep` (exact CAD geometry) or `mesh` (generated triangle mesh, for comparing with STL). |
| `--mesh-deflection` | `auto` | STEP mesh fineness: `auto` (fast), `auto-precise` (finer, slower), or a number in the output unit. |
| `--angular-deflection` | `auto` | Largest angle between mesh triangles, in radians. `auto` follows `--mesh-deflection`. |
| `--base-tolerance` | `1e-6` | How close to the rear end a face must be to count as base area, as a fraction of the model size. |
| `--out`, `-o` | none | Save results to this CSV file (`measure`, `project`, `sweep`). |

The mesh options only affect STEP files. See [Accuracy and Mesh Settings](accuracy.md) for when
to change them.

## Examples

Convert an STL exported in millimeters and report in meters:

```bash
cadmetrics measure model.stl --unit mm --output-unit m
```

A STEP model whose "up" is its Y axis:

```bash
cadmetrics project model.step --axis-map x,-z,y --alpha 10
```

A precise sweep for final numbers:

```bash
cadmetrics sweep model.step \
  --mesh-deflection auto-precise \
  --alpha 0:180:5 \
  --beta 0:90:5 \
  --out sweep_precise.csv
```
