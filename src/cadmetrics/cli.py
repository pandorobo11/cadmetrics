from __future__ import annotations

import csv
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cadmetrics.api import inspect_model
from cadmetrics.api import measure as measure_api
from cadmetrics.api import project as project_api
from cadmetrics.api import sweep as sweep_api
from cadmetrics.types import MeasurementRow

app = typer.Typer(no_args_is_help=True, help="Calculate CAD volume, surface, and projected area.")
console = Console()

CSV_FIELDS = [
    "file",
    "input_unit",
    "output_unit",
    "roll_deg",
    "alpha_deg",
    "beta_deg",
    "volume",
    "surface_area",
    "projected_area",
    "is_watertight",
    "warnings",
]


@app.command()
def measure(
    file: Path = typer.Argument(..., exists=True, readable=True, help="STL or STEP file."),
    unit: str = typer.Option("m", "--unit", help="Input length unit."),
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
    alpha: float = typer.Option(0.0, "--alpha", help="Angle of attack in degrees."),
    beta: float = typer.Option(0.0, "--beta", help="Sideslip angle in degrees."),
    direction: str | None = typer.Option(
        None,
        "--direction",
        help="Projection direction vector, e.g. 1,0,0. Overrides attitude angles.",
    ),
    unit: str = typer.Option("m", "--unit", help="Input length unit."),
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
    alpha: str = typer.Option("0", "--alpha", help="Angle of attack degrees as value or range."),
    beta: str = typer.Option("0", "--beta", help="Sideslip degrees as value or range."),
    unit: str = typer.Option("m", "--unit", help="Input length unit."),
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
    """Calculate projected area for every combination of roll, alpha, and beta."""

    rows = _run_or_exit(
        lambda: sweep_api(
            file,
            roll=roll,
            alpha=alpha,
            beta=beta,
            input_unit=unit,
            output_unit=output_unit,
            mesh_deflection=mesh_deflection,
            angular_deflection=angular_deflection,
        )
    )
    _emit_rows(rows, out)


@app.command()
def inspect(
    file: Path = typer.Argument(..., exists=True, readable=True, help="STL or STEP file."),
    unit: str = typer.Option("m", "--unit", help="Input length unit."),
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
