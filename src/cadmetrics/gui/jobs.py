from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from cadmetrics.api import measure, project, sweep
from cadmetrics.orientation import Orientation
from cadmetrics.types import MeasurementRow

CalculationMode = Literal["measure", "project", "sweep"]


@dataclass(frozen=True)
class CalculationRequest:
    file: Path
    mode: CalculationMode
    input_unit: str = "auto"
    output_unit: str = "m"
    mesh_deflection: float = 1.0e-3
    angular_deflection: float = 0.1
    roll: str = "0"
    alpha: str = "0"
    beta: str = "0"
    direction: str | None = None


def run_calculation(
    request: CalculationRequest,
    *,
    progress_callback: Callable[[int, int, Orientation], None] | None = None,
) -> list[MeasurementRow]:
    common = {
        "input_unit": request.input_unit,
        "output_unit": request.output_unit,
        "mesh_deflection": request.mesh_deflection,
        "angular_deflection": request.angular_deflection,
    }
    if request.mode == "measure":
        return [measure(request.file, **common)]
    if request.mode == "project":
        return [
            project(
                request.file,
                roll_deg=float(request.roll),
                alpha_deg=float(request.alpha),
                beta_deg=float(request.beta),
                direction=request.direction.strip() if request.direction else None,
                **common,
            )
        ]
    return sweep(
        request.file,
        roll=request.roll,
        alpha=request.alpha,
        beta=request.beta,
        progress_callback=progress_callback,
        **common,
    )

