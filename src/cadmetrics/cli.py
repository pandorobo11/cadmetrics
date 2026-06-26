from __future__ import annotations

import csv
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from cadmetrics.orientation import Orientation
from cadmetrics.api import inspect_model
from cadmetrics.api import measure as measure_api
from cadmetrics.api import project as project_api
from cadmetrics.api import sweep as sweep_api
from cadmetrics.types import MeasurementRow

app = typer.Typer(no_args_is_help=True, help="Calculate CAD volume, surface, and projected area.")
console = Console()
err_console = Console(stderr=True)

CSV_FIELDS = [
    "file",
    "input_unit",
    "output_unit",
    "roll_deg",
    "alpha_deg",
    "beta_deg",
    "direction_x",
    "direction_y",
    "direction_z",
    "volume",
    "surface_area",
    "projected_area",
    "is_watertight",
    "mesh_deflection",
    "angular_deflection",
    "method",
    "elapsed_sec",
    "warnings",
]


@app.command()
def measure(
    file: Path = typer.Argument(..., exists=True, readable=True, help="STL or STEP file."),
    unit: str = typer.Option(
        "auto",
        "--unit",
        help="Input length unit. Use 'auto' to read STEP units and assume m for STL.",
    ),
    output_unit: str = typer.Option("m", "--output-unit", help="Output length unit."),
    mesh_deflection: float = typer.Option(
        1.0e-3,
        "--mesh-deflection",
        min=0.0,
        help="STEP tessellation tolerance in output length units.",
    ),
    angular_deflection: float = typer.Option(
        0.1,
        "--angular-deflection",
        min=0.0,
        help="STEP tessellation angular tolerance.",
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
        )
    )
    _emit_rows([row], out)


@app.command()
def project(
    file: Path = typer.Argument(..., exists=True, readable=True, help="STL or STEP file."),
    roll: float = typer.Option(0.0, "--roll", help="Roll angle in degrees."),
    alpha: float = typer.Option(
        0.0,
        "--alpha",
        help="Projection-direction angle of attack in degrees, not plane inclination.",
    ),
    beta: float = typer.Option(0.0, "--beta", help="Sideslip angle in degrees."),
    direction: str | None = typer.Option(
        None,
        "--direction",
        help="Projection direction vector, e.g. 1,0,0. Overrides attitude angles.",
    ),
    unit: str = typer.Option(
        "auto",
        "--unit",
        help="Input length unit. Use 'auto' to read STEP units and assume m for STL.",
    ),
    output_unit: str = typer.Option("m", "--output-unit", help="Output length unit."),
    mesh_deflection: float = typer.Option(
        1.0e-3,
        "--mesh-deflection",
        min=0.0,
        help="STEP tessellation tolerance in output length units.",
    ),
    angular_deflection: float = typer.Option(
        0.1,
        "--angular-deflection",
        min=0.0,
        help="STEP tessellation angular tolerance.",
    ),
    out: Path | None = typer.Option(None, "--out", "-o", help="CSV output path."),
) -> None:
    """Calculate projected area for one attitude or vector direction."""

    row = _run_or_exit(
        lambda: project_api(
            file,
            roll_deg=roll,
            alpha_deg=alpha,
            beta_deg=beta,
            direction=direction,
            input_unit=unit,
            output_unit=output_unit,
            mesh_deflection=mesh_deflection,
            angular_deflection=angular_deflection,
        )
    )
    _emit_rows([row], out)


@app.command()
def sweep(
    file: Path = typer.Argument(..., exists=True, readable=True, help="STL or STEP file."),
    roll: str = typer.Option("0", "--roll", help="Roll degrees as value or start:end:step."),
    alpha: str = typer.Option(
        "0",
        "--alpha",
        help="Projection-direction angle of attack degrees as value or start:end:step.",
    ),
    beta: str = typer.Option("0", "--beta", help="Sideslip degrees as value or range."),
    unit: str = typer.Option(
        "auto",
        "--unit",
        help="Input length unit. Use 'auto' to read STEP units and assume m for STL.",
    ),
    output_unit: str = typer.Option("m", "--output-unit", help="Output length unit."),
    mesh_deflection: float = typer.Option(
        1.0e-3,
        "--mesh-deflection",
        min=0.0,
        help="STEP tessellation tolerance in output length units.",
    ),
    angular_deflection: float = typer.Option(
        0.1,
        "--angular-deflection",
        min=0.0,
        help="STEP tessellation angular tolerance.",
    ),
    out: Path | None = typer.Option(None, "--out", "-o", help="CSV output path."),
    summary: bool = typer.Option(True, "--summary/--no-summary", help="Print sweep summary."),
) -> None:
    """Calculate projected area for every combination of roll, alpha, and beta."""

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=err_console,
    )
    task_id: int | None = None

    def on_progress(index: int, total: int, orientation: Orientation) -> None:
        nonlocal task_id
        if task_id is None:
            task_id = progress.add_task("sweep", total=total)
        progress.update(
            task_id,
            completed=index,
            description=(
                f"roll={orientation.roll_deg:g} "
                f"alpha={orientation.alpha_deg:g} "
                f"beta={orientation.beta_deg:g}"
            ),
        )

    rows = _run_or_exit(
        lambda: _run_with_progress(
            progress,
            lambda: sweep_api(
                file,
                roll=roll,
                alpha=alpha,
                beta=beta,
                input_unit=unit,
                output_unit=output_unit,
                mesh_deflection=mesh_deflection,
                angular_deflection=angular_deflection,
                progress_callback=on_progress,
            ),
        )
    )
    _emit_rows(rows, out)
    if summary:
        _emit_sweep_summary(rows)


@app.command()
def inspect(
    file: Path = typer.Argument(..., exists=True, readable=True, help="STL or STEP file."),
    unit: str = typer.Option(
        "auto",
        "--unit",
        help="Input length unit. Use 'auto' to read STEP units and assume m for STL.",
    ),
    output_unit: str = typer.Option("m", "--output-unit", help="Output length unit."),
    mesh_deflection: float = typer.Option(
        1.0e-3,
        "--mesh-deflection",
        min=0.0,
        help="STEP tessellation tolerance in output length units.",
    ),
    angular_deflection: float = typer.Option(
        0.1,
        "--angular-deflection",
        min=0.0,
        help="STEP tessellation angular tolerance.",
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
        )
    )
    table = Table(title=str(model.path))
    table.add_column("field")
    table.add_column("value")
    table.add_row("input_unit", model.input_unit)
    table.add_row("output_unit", model.output_unit)
    table.add_row("source_format", model.source_format)
    table.add_row("vertices", str(model.vertex_count))
    table.add_row("faces", str(model.face_count))
    table.add_row("volume", _format_optional(model.volume))
    table.add_row("surface_area", _format_optional(model.surface_area))
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
    table.add_column("alpha")
    table.add_column("beta")
    table.add_row(
        "min",
        _format_optional(min_row.projected_area),
        _format_optional(min_row.roll_deg),
        _format_optional(min_row.alpha_deg),
        _format_optional(min_row.beta_deg),
    )
    table.add_row(
        "max",
        _format_optional(max_row.projected_area),
        _format_optional(max_row.roll_deg),
        _format_optional(max_row.alpha_deg),
        _format_optional(max_row.beta_deg),
    )
    table.add_row("avg", _format_optional(average), "", "", "")
    err_console.print(table)


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
        console.print(f"[red]Error:[/red] {exc}", stderr=True)
        raise typer.Exit(code=1) from exc
