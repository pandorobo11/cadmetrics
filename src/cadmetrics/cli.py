from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import cast

import typer
from rich.console import Console
from rich.markup import escape
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from cadmetrics.api import AttitudeMode, StepComponentMode, inspect_model
from cadmetrics.api import measure as measure_api
from cadmetrics.api import project as project_api
from cadmetrics.api import sweep as sweep_api
from cadmetrics.coordinates import DEFAULT_AXIS_MAP
from cadmetrics.io import DEFAULT_BASE_TOLERANCE
from cadmetrics.sweep import parse_sweep_values
from cadmetrics.types import MeasurementRow

app = typer.Typer(no_args_is_help=True, help="Calculate CAD volume, surface, and projected area.")
console = Console()
err_console = Console(stderr=True)
ATTITUDE_MODES = ("alpha-beta", "roll-pitch", "vector")

CSV_FIELDS = [
    "file",
    "step_components",
    "step_component_names",
    "input_unit",
    "output_unit",
    "roll_deg",
    "pitch_deg",
    "alpha_deg",
    "beta_deg",
    "direction_x",
    "direction_y",
    "direction_z",
    "x_min",
    "x_max",
    "y_min",
    "y_max",
    "z_min",
    "z_max",
    "surface_area",
    "newly_exposed_surface_area",
    "base_area",
    "volume",
    "projected_area",
    "centroid_u",
    "centroid_v",
    "centroid_x",
    "centroid_y",
    "centroid_z",
    "is_watertight",
    "mesh_deflection",
    "angular_deflection",
    "base_tolerance",
    "step_component_mode",
    "method",
    "load_elapsed_sec",
    "elapsed_sec",
    "cadmetrics_version",
    "cadmetrics_hash",
    "warnings",
]


@app.command()
def measure(
    file: list[Path] = typer.Argument(..., exists=True, readable=True, help="STL or STEP file(s)."),
    unit: str = typer.Option(
        "auto",
        "--unit",
        help="Input length unit. Use 'auto' to read STEP units and assume m for STL.",
    ),
    output_unit: str = typer.Option("m", "--output-unit", help="Output length unit."),
    mesh_deflection: str = typer.Option(
        "auto",
        "--mesh-deflection",
        help="STEP tessellation tolerance in output length units, or 'auto' for bbox diagonal * 1e-4.",
    ),
    angular_deflection: float = typer.Option(
        0.1,
        "--angular-deflection",
        min=0.0,
        help="STEP tessellation angular tolerance.",
    ),
    base_tolerance: float = typer.Option(
        DEFAULT_BASE_TOLERANCE,
        "--base-tolerance",
        min=0.0,
        help="Relative tolerance for identifying Xmax base faces: max(bbox diagonal * value, 1e-12).",
    ),
    axis_map: str = typer.Option(
        DEFAULT_AXIS_MAP,
        "--axis-map",
        help="Map cadmetrics X,Y,Z to input axes, e.g. x,y,z or x,-z,y.",
    ),
    step_metrics: str = typer.Option(
        "brep",
        "--step-metrics",
        help="STEP volume/surface metric source: 'brep' for CAD-kernel values or 'mesh' for tessellated mesh values.",
    ),
    step_component: list[int] | None = typer.Option(
        None,
        "--step-component",
        min=1,
        help="1-based STEP component to enable; repeat for multiple components.",
    ),
    component_mode: str = typer.Option(
        "filter",
        "--component-mode",
        help="STEP component handling: 'filter' hides disabled components; 'subtract' cuts them out.",
    ),
    out: Path | None = typer.Option(None, "--out", "-o", help="CSV output path."),
) -> None:
    """Calculate volume and surface area."""

    row = _run_or_exit(
        lambda: measure_api(
            file,
            input_unit=unit,
            output_unit=output_unit,
            mesh_deflection=mesh_deflection,
            angular_deflection=angular_deflection,
            base_tolerance=base_tolerance,
            axis_map=axis_map,
            step_metric_source=step_metrics,
            step_components=_component_selection(step_component),
            step_component_mode=cast(StepComponentMode, component_mode),
        )
    )
    if out is None:
        _emit_measurement_table(row, title=_format_input_files(file))
    else:
        _emit_rows([row], out)


@app.command()
def project(
    file: list[Path] = typer.Argument(..., exists=True, readable=True, help="STL or STEP file(s)."),
    attitude: str | None = typer.Option(
        None,
        "--attitude",
        help="Attitude input mode: alpha-beta, roll-pitch, or vector.",
    ),
    alpha: float = typer.Option(
        0.0,
        "--alpha",
        help="Alpha angle in degrees for --attitude alpha-beta.",
    ),
    beta: float = typer.Option(0.0, "--beta", help="Beta angle in degrees for --attitude alpha-beta."),
    roll: float = typer.Option(0.0, "--roll", help="Roll angle in degrees for --attitude roll-pitch."),
    pitch: float | None = typer.Option(
        None,
        "--pitch",
        help="Pitch angle in degrees for --attitude roll-pitch.",
    ),
    direction: str | None = typer.Option(
        None,
        "--direction",
        help="Projection direction vector for --attitude vector, e.g. 1,0,0.",
    ),
    unit: str = typer.Option(
        "auto",
        "--unit",
        help="Input length unit. Use 'auto' to read STEP units and assume m for STL.",
    ),
    output_unit: str = typer.Option("m", "--output-unit", help="Output length unit."),
    mesh_deflection: str = typer.Option(
        "auto",
        "--mesh-deflection",
        help="STEP tessellation tolerance in output length units, or 'auto' for bbox diagonal * 1e-4.",
    ),
    angular_deflection: float = typer.Option(
        0.1,
        "--angular-deflection",
        min=0.0,
        help="STEP tessellation angular tolerance.",
    ),
    base_tolerance: float = typer.Option(
        DEFAULT_BASE_TOLERANCE,
        "--base-tolerance",
        min=0.0,
        help="Relative tolerance for identifying Xmax base faces: max(bbox diagonal * value, 1e-12).",
    ),
    axis_map: str = typer.Option(
        DEFAULT_AXIS_MAP,
        "--axis-map",
        help="Map cadmetrics X,Y,Z to input axes, e.g. x,y,z or x,-z,y.",
    ),
    step_metrics: str = typer.Option(
        "brep",
        "--step-metrics",
        help="STEP volume/surface metric source: 'brep' for CAD-kernel values or 'mesh' for tessellated mesh values.",
    ),
    step_component: list[int] | None = typer.Option(
        None,
        "--step-component",
        min=1,
        help="1-based STEP component to enable; repeat for multiple components.",
    ),
    component_mode: str = typer.Option(
        "filter",
        "--component-mode",
        help="STEP component handling: 'filter' hides disabled components; 'subtract' cuts them out.",
    ),
    out: Path | None = typer.Option(None, "--out", "-o", help="CSV output path."),
) -> None:
    """Calculate projected area for one attitude or vector direction."""

    request = _resolve_project_attitude(
        attitude=attitude,
        alpha=alpha,
        beta=beta,
        roll=roll,
        pitch=pitch,
        direction=direction,
    )
    row = _run_or_exit(
        lambda: project_api(
            file,
            attitude=cast(AttitudeMode, request["mode"]),
            roll_deg=request["roll"],
            pitch_deg=request["pitch"],
            alpha_deg=request["alpha"],
            beta_deg=request["beta"],
            direction=request["direction"],
            input_unit=unit,
            output_unit=output_unit,
            mesh_deflection=mesh_deflection,
            angular_deflection=angular_deflection,
            base_tolerance=base_tolerance,
            axis_map=axis_map,
            step_metric_source=step_metrics,
            step_components=_component_selection(step_component),
            step_component_mode=cast(StepComponentMode, component_mode),
        )
    )
    if out is None:
        _emit_measurement_table(row, title=_format_input_files(file))
    else:
        _emit_rows([row], out)


@app.command()
def sweep(
    file: list[Path] = typer.Argument(..., exists=True, readable=True, help="STL or STEP file(s)."),
    attitude: str | None = typer.Option(
        None,
        "--attitude",
        help="Attitude input mode: alpha-beta, roll-pitch, or vector.",
    ),
    alpha: str = typer.Option(
        "0",
        "--alpha",
        help="Alpha degrees for --attitude alpha-beta as value or start/end/step range.",
    ),
    beta: str = typer.Option(
        "0",
        "--beta",
        help="Beta degrees for --attitude alpha-beta as value or start/end/step range.",
    ),
    roll: str = typer.Option(
        "0",
        "--roll",
        help="Roll degrees for --attitude roll-pitch as value or start/end/step range.",
    ),
    pitch: str | None = typer.Option(
        None,
        "--pitch",
        help="Pitch degrees for --attitude roll-pitch as value or start/end/step range.",
    ),
    direction: str | None = typer.Option(
        None,
        "--direction",
        help="Projection direction vector for --attitude vector, e.g. 1,0,0.",
    ),
    unit: str = typer.Option(
        "auto",
        "--unit",
        help="Input length unit. Use 'auto' to read STEP units and assume m for STL.",
    ),
    output_unit: str = typer.Option("m", "--output-unit", help="Output length unit."),
    mesh_deflection: str = typer.Option(
        "auto",
        "--mesh-deflection",
        help="STEP tessellation tolerance in output length units, or 'auto' for bbox diagonal * 1e-4.",
    ),
    angular_deflection: float = typer.Option(
        0.1,
        "--angular-deflection",
        min=0.0,
        help="STEP tessellation angular tolerance.",
    ),
    base_tolerance: float = typer.Option(
        DEFAULT_BASE_TOLERANCE,
        "--base-tolerance",
        min=0.0,
        help="Relative tolerance for identifying Xmax base faces: max(bbox diagonal * value, 1e-12).",
    ),
    axis_map: str = typer.Option(
        DEFAULT_AXIS_MAP,
        "--axis-map",
        help="Map cadmetrics X,Y,Z to input axes, e.g. x,y,z or x,-z,y.",
    ),
    step_metrics: str = typer.Option(
        "brep",
        "--step-metrics",
        help="STEP volume/surface metric source: 'brep' for CAD-kernel values or 'mesh' for tessellated mesh values.",
    ),
    step_component: list[int] | None = typer.Option(
        None,
        "--step-component",
        min=1,
        help="1-based STEP component to enable; repeat for multiple components.",
    ),
    component_mode: str = typer.Option(
        "filter",
        "--component-mode",
        help="STEP component handling: 'filter' hides disabled components; 'subtract' cuts them out.",
    ),
    out: Path | None = typer.Option(None, "--out", "-o", help="CSV output path."),
    summary: bool = typer.Option(True, "--summary/--no-summary", help="Print sweep summary."),
) -> None:
    """Calculate projected area for attitude sweeps or one vector direction."""

    request = _resolve_sweep_attitude(
        attitude=attitude,
        alpha=alpha,
        beta=beta,
        roll=roll,
        pitch=pitch,
        direction=direction,
    )

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=err_console,
    )
    task_id: int | None = None

    def on_progress(index: int, total: int, row: MeasurementRow) -> None:
        nonlocal task_id
        if task_id is None:
            task_id = progress.add_task("sweep", total=total)
        progress.update(
            task_id,
            completed=index,
            description=(
                f"roll={row.roll_deg:g} "
                f"pitch={row.pitch_deg:g} "
                f"alpha={row.alpha_deg:g} "
                f"beta={row.beta_deg:g}"
            ),
        )

    if request["mode"] == "vector":
        row = _run_or_exit(
            lambda: project_api(
                file,
                attitude="vector",
                direction=request["direction"],
                input_unit=unit,
                output_unit=output_unit,
                mesh_deflection=mesh_deflection,
                angular_deflection=angular_deflection,
                base_tolerance=base_tolerance,
                axis_map=axis_map,
                step_metric_source=step_metrics,
                step_components=_component_selection(step_component),
                step_component_mode=cast(StepComponentMode, component_mode),
            )
        )
        rows = [row]
    else:
        rows = _run_or_exit(
            lambda: _run_with_progress(
                progress,
                lambda: sweep_api(
                    file,
                    attitude=cast(AttitudeMode, request["mode"]),
                    roll_deg=request["roll"],
                    pitch_deg=request["pitch"],
                    alpha_deg=request["alpha"],
                    beta_deg=request["beta"],
                    input_unit=unit,
                    output_unit=output_unit,
                    mesh_deflection=mesh_deflection,
                    angular_deflection=angular_deflection,
                    base_tolerance=base_tolerance,
                    axis_map=axis_map,
                    step_metric_source=step_metrics,
                    step_components=_component_selection(step_component),
                    step_component_mode=cast(StepComponentMode, component_mode),
                    progress_callback=on_progress,
                ),
            )
        )
    _emit_rows(rows, out)
    if summary:
        _emit_sweep_summary(rows)


@app.command()
def inspect(
    file: list[Path] = typer.Argument(..., exists=True, readable=True, help="STL or STEP file(s)."),
    unit: str = typer.Option(
        "auto",
        "--unit",
        help="Input length unit. Use 'auto' to read STEP units and assume m for STL.",
    ),
    output_unit: str = typer.Option("m", "--output-unit", help="Output length unit."),
    mesh_deflection: str = typer.Option(
        "auto",
        "--mesh-deflection",
        help="STEP tessellation tolerance in output length units, or 'auto' for bbox diagonal * 1e-4.",
    ),
    angular_deflection: float = typer.Option(
        0.1,
        "--angular-deflection",
        min=0.0,
        help="STEP tessellation angular tolerance.",
    ),
    base_tolerance: float = typer.Option(
        DEFAULT_BASE_TOLERANCE,
        "--base-tolerance",
        min=0.0,
        help="Relative tolerance for identifying Xmax base faces: max(bbox diagonal * value, 1e-12).",
    ),
    axis_map: str = typer.Option(
        DEFAULT_AXIS_MAP,
        "--axis-map",
        help="Map cadmetrics X,Y,Z to input axes, e.g. x,y,z or x,-z,y.",
    ),
    step_metrics: str = typer.Option(
        "brep",
        "--step-metrics",
        help="STEP volume/surface metric source: 'brep' for CAD-kernel values or 'mesh' for tessellated mesh values.",
    ),
    step_component: list[int] | None = typer.Option(
        None,
        "--step-component",
        min=1,
        help="1-based STEP component to enable; repeat for multiple components.",
    ),
    component_mode: str = typer.Option(
        "filter",
        "--component-mode",
        help="STEP component handling: 'filter' hides disabled components; 'subtract' cuts them out.",
    ),
) -> None:
    """Show loaded model information."""

    model = _run_or_exit(
        lambda: inspect_model(
            file,
            input_unit=unit,
            output_unit=output_unit,
            mesh_deflection=mesh_deflection,
            angular_deflection=angular_deflection,
            base_tolerance=base_tolerance,
            axis_map=axis_map,
            step_metric_source=step_metrics,
            step_components=_component_selection(step_component),
            step_component_mode=cast(StepComponentMode, component_mode),
            require_mesh=step_metrics.strip().lower().replace("_", "-")
            in {"mesh", "tessellated", "stl"},
        )
    )
    table = Table(title=_format_input_files(file))
    table.add_column("field")
    table.add_column("value")
    table.add_row("input_unit", model.input_unit)
    table.add_row("output_unit", model.output_unit)
    table.add_row("source_format", model.source_format)
    table.add_row("assembly", str(model.is_assembly))
    if model.step_metric_source:
        table.add_row("step_metrics", model.step_metric_source)
    if model.step_component_mode:
        table.add_row("component_mode", model.step_component_mode)
    table.add_row("vertices", str(model.vertex_count))
    table.add_row("faces", str(model.face_count))
    table.add_row("x_min", _format_optional(model.x_min))
    table.add_row("x_max", _format_optional(model.x_max))
    table.add_row("y_min", _format_optional(model.y_min))
    table.add_row("y_max", _format_optional(model.y_max))
    table.add_row("z_min", _format_optional(model.z_min))
    table.add_row("z_max", _format_optional(model.z_max))
    table.add_row("surface_area", _format_optional(model.surface_area))
    table.add_row(
        "newly_exposed_surface_area",
        _format_optional(model.newly_exposed_surface_area),
    )
    table.add_row("base_area", _format_optional(model.base_area))
    table.add_row("volume", _format_optional(model.volume))
    if model.component_names:
        table.add_row(
            "components",
            f"{len(model.selected_components)} of {len(model.component_names)}",
        )
        table.add_row(
            "component_list",
            "\n".join(
                f"{index}: {name}"
                for index, name in enumerate(model.component_names, start=1)
            ),
        )
    table.add_row("cadmetrics_version", model.cadmetrics_version)
    table.add_row("cadmetrics_hash", model.cadmetrics_hash)
    table.add_row("base_tolerance", _format_optional(model.base_tolerance))
    table.add_row("is_watertight", str(model.is_watertight))
    table.add_row("warnings", "; ".join(model.warnings))
    console.print(table)


def _emit_rows(rows: list[MeasurementRow], out: Path | None) -> None:
    if out is None:
        writer = csv.DictWriter(sys.stdout, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())
        return

    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())
    console.print(f"Wrote {len(rows)} row(s) to {out}")


def _format_input_files(files: list[Path]) -> str:
    if len(files) == 1:
        return str(files[0])
    return " + ".join(str(file) for file in files)


def _component_selection(values: list[int] | None) -> tuple[int, ...] | None:
    if values is None:
        return None
    return tuple(dict.fromkeys(values))


def _emit_measurement_table(row: MeasurementRow, *, title: str) -> None:
    table = Table(title=title)
    table.add_column("field")
    table.add_column("value")
    table.add_row("input_unit", row.input_unit)
    table.add_row("output_unit", row.output_unit)
    table.add_row("assembly", str("assembly" in (row.method or "")))
    table.add_row("x_min", _format_optional(row.x_min))
    table.add_row("x_max", _format_optional(row.x_max))
    table.add_row("y_min", _format_optional(row.y_min))
    table.add_row("y_max", _format_optional(row.y_max))
    table.add_row("z_min", _format_optional(row.z_min))
    table.add_row("z_max", _format_optional(row.z_max))
    table.add_row("surface_area", _format_optional(row.surface_area))
    table.add_row(
        "newly_exposed_surface_area",
        _format_optional(row.newly_exposed_surface_area),
    )
    table.add_row("base_area", _format_optional(row.base_area))
    table.add_row("volume", _format_optional(row.volume))
    if row.projected_area is not None:
        table.add_row("projected_area", _format_optional(row.projected_area))
        table.add_row("centroid_u", _format_optional(row.centroid_u))
        table.add_row("centroid_v", _format_optional(row.centroid_v))
        table.add_row("centroid_x", _format_optional(row.centroid_x))
        table.add_row("centroid_y", _format_optional(row.centroid_y))
        table.add_row("centroid_z", _format_optional(row.centroid_z))
        table.add_row("roll_deg", _format_optional(row.roll_deg))
        table.add_row("pitch_deg", _format_optional(row.pitch_deg))
        table.add_row("alpha_deg", _format_optional(row.alpha_deg))
        table.add_row("beta_deg", _format_optional(row.beta_deg))
        table.add_row("direction_x", _format_optional(row.direction_x))
        table.add_row("direction_y", _format_optional(row.direction_y))
        table.add_row("direction_z", _format_optional(row.direction_z))
    table.add_row("is_watertight", str(row.is_watertight))
    table.add_row("mesh_deflection", _format_optional(row.mesh_deflection))
    table.add_row("angular_deflection", _format_optional(row.angular_deflection))
    table.add_row("base_tolerance", _format_optional(row.base_tolerance))
    table.add_row("component_mode", row.step_component_mode or "")
    table.add_row("method", row.method or "")
    table.add_row("load_elapsed_sec", _format_optional(row.load_elapsed_sec))
    table.add_row("elapsed_sec", _format_optional(row.elapsed_sec))
    table.add_row("cadmetrics_version", row.cadmetrics_version)
    table.add_row("cadmetrics_hash", row.cadmetrics_hash)
    table.add_row("warnings", "; ".join(row.warnings))
    console.print(table)


def _emit_sweep_summary(rows: list[MeasurementRow]) -> None:
    projected_rows = [row for row in rows if row.projected_area is not None]
    if not projected_rows:
        return

    min_row = min(projected_rows, key=lambda row: row.projected_area or 0.0)
    max_row = max(projected_rows, key=lambda row: row.projected_area or 0.0)
    average = sum(row.projected_area or 0.0 for row in projected_rows) / len(projected_rows)

    table = Table(title="Sweep Summary")
    table.add_column("metric")
    table.add_column("projected_area")
    table.add_column("roll")
    table.add_column("pitch")
    table.add_column("alpha")
    table.add_column("beta")
    table.add_row(
        "min",
        _format_optional(min_row.projected_area),
        _format_optional(min_row.roll_deg),
        _format_optional(min_row.pitch_deg),
        _format_optional(min_row.alpha_deg),
        _format_optional(min_row.beta_deg),
    )
    table.add_row(
        "max",
        _format_optional(max_row.projected_area),
        _format_optional(max_row.roll_deg),
        _format_optional(max_row.pitch_deg),
        _format_optional(max_row.alpha_deg),
        _format_optional(max_row.beta_deg),
    )
    table.add_row("avg", _format_optional(average), "", "", "", "")
    err_console.print(table)


def _resolve_project_attitude(
    *,
    attitude: str | None,
    alpha: float,
    beta: float,
    roll: float,
    pitch: float | None,
    direction: str | None,
) -> dict[str, float | str | None]:
    mode = _normalize_attitude_mode(attitude, pitch=pitch, direction=direction)
    if mode == "vector":
        if direction is None:
            raise typer.BadParameter("--direction is required when --attitude vector is used")
        _reject_nonzero(alpha, "--alpha", mode)
        _reject_nonzero(beta, "--beta", mode)
        _reject_nonzero(roll, "--roll", mode)
        if pitch is not None:
            _reject_nonzero(pitch, "--pitch", mode)
        return {
            "mode": mode,
            "roll": 0.0,
            "pitch": 0.0,
            "alpha": 0.0,
            "beta": 0.0,
            "direction": direction,
        }

    if direction is not None:
        raise typer.BadParameter("--direction can only be used with --attitude vector")
    if mode == "roll-pitch":
        _reject_nonzero(alpha, "--alpha", mode)
        _reject_nonzero(beta, "--beta", mode)
        return {
            "mode": mode,
            "roll": roll,
            "pitch": 0.0 if pitch is None else pitch,
            "alpha": 0.0,
            "beta": 0.0,
            "direction": None,
        }

    if pitch is not None:
        raise typer.BadParameter("--pitch can only be used with --attitude roll-pitch")
    _reject_nonzero(roll, "--roll", mode)
    return {
        "mode": mode,
        "roll": 0.0,
        "pitch": 0.0,
        "alpha": alpha,
        "beta": beta,
        "direction": None,
    }


def _resolve_sweep_attitude(
    *,
    attitude: str | None,
    alpha: str,
    beta: str,
    roll: str,
    pitch: str | None,
    direction: str | None,
) -> dict[str, str | float | None]:
    mode = _normalize_attitude_mode(attitude, pitch=pitch, direction=direction)
    if mode == "vector":
        if direction is None:
            raise typer.BadParameter("--direction is required when --attitude vector is used")
        _reject_nondefault_spec(alpha, "--alpha", mode)
        _reject_nondefault_spec(beta, "--beta", mode)
        _reject_nondefault_spec(roll, "--roll", mode)
        if pitch is not None:
            _reject_nondefault_spec(pitch, "--pitch", mode)
        return {
            "mode": mode,
            "roll": "0",
            "pitch": "0",
            "alpha": "0",
            "beta": "0",
            "direction": direction,
        }

    if direction is not None:
        raise typer.BadParameter("--direction can only be used with --attitude vector")
    if mode == "roll-pitch":
        _reject_nondefault_spec(alpha, "--alpha", mode)
        _reject_nondefault_spec(beta, "--beta", mode)
        return {
            "mode": mode,
            "roll": roll,
            "pitch": "0" if pitch is None else pitch,
            "alpha": "0",
            "beta": 0.0,
            "direction": None,
        }

    if pitch is not None:
        raise typer.BadParameter("--pitch can only be used with --attitude roll-pitch")
    _reject_nondefault_spec(roll, "--roll", mode)
    return {
        "mode": mode,
        "roll": "0",
        "pitch": "0",
        "alpha": alpha,
        "beta": beta,
        "direction": None,
    }


def _normalize_attitude_mode(
    attitude: str | None,
    *,
    pitch: float | str | None,
    direction: str | None,
) -> str:
    if attitude is None:
        if direction is not None:
            return "vector"
        if pitch is not None:
            return "roll-pitch"
        return "alpha-beta"
    mode = attitude.strip().lower().replace("_", "-")
    if mode not in ATTITUDE_MODES:
        raise typer.BadParameter(
            f"--attitude must be one of: {', '.join(ATTITUDE_MODES)}"
        )
    return mode


def _reject_nonzero(value: float, option: str, mode: str) -> None:
    if value != 0.0:
        raise typer.BadParameter(f"{option} cannot be used with --attitude {mode}")


def _reject_nondefault_spec(value: str, option: str, mode: str) -> None:
    if parse_sweep_values(value) != [0.0]:
        raise typer.BadParameter(f"{option} cannot be used with --attitude {mode}")


def _run_with_progress(progress: Progress, action):
    with progress:
        return action()


def _format_optional(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.12g}"


def _run_or_exit(action):
    try:
        return action()
    except Exception as exc:
        err_console.print(f"[red]Error:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc
