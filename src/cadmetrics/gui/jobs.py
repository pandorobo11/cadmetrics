from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from cadmetrics.api import project, sweep
from cadmetrics.coordinates import DEFAULT_AXIS_MAP
from cadmetrics.types import MeasurementRow

AttitudeInputMode = Literal["alpha_beta", "roll_pitch", "vector"]
ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class CalculationRequest:
    file: Path
    attitude_mode: AttitudeInputMode = "alpha_beta"
    input_unit: str = "auto"
    output_unit: str = "m"
    mesh_deflection: float | str = "auto"
    angular_deflection: float = 0.1
    axis_map: str = DEFAULT_AXIS_MAP
    step_metric_source: str = "brep"
    step_components: tuple[int, ...] | None = None
    roll_start: float = 0.0
    roll_end: float = 0.0
    roll_step: float = 1.0
    alpha_start: float = 0.0
    alpha_end: float = 0.0
    alpha_step: float = 1.0
    beta_start: float = 0.0
    beta_end: float = 0.0
    beta_step: float = 1.0
    pitch_start: float = 0.0
    pitch_end: float = 0.0
    pitch_step: float = 1.0
    vector_x: float = 1.0
    vector_y: float = 0.0
    vector_z: float = 0.0


def run_calculation(
    request: CalculationRequest,
    *,
    progress_callback: ProgressCallback | None = None,
) -> list[MeasurementRow]:
    common = {
        "input_unit": request.input_unit,
        "output_unit": request.output_unit,
        "mesh_deflection": request.mesh_deflection,
        "angular_deflection": request.angular_deflection,
        "axis_map": request.axis_map,
        "step_metric_source": request.step_metric_source,
        "step_components": request.step_components,
    }
    if request.attitude_mode == "alpha_beta":
        return sweep(
            request.file,
            roll=0.0,
            alpha=_range_spec(request.alpha_start, request.alpha_end, request.alpha_step),
            beta=_range_spec(request.beta_start, request.beta_end, request.beta_step),
            progress_callback=_orientation_progress(progress_callback),
            **common,
        )
    if request.attitude_mode == "roll_pitch":
        return sweep(
            request.file,
            roll=_range_spec(request.roll_start, request.roll_end, request.roll_step),
            alpha=_range_spec(request.pitch_start, request.pitch_end, request.pitch_step),
            beta=0.0,
            progress_callback=_orientation_progress(progress_callback),
            **common,
        )

    row = project(
        request.file,
        direction=f"{request.vector_x},{request.vector_y},{request.vector_z}",
        **common,
    )
    if progress_callback is not None:
        progress_callback(
            1,
            1,
            f"vector=({request.vector_x:g}, {request.vector_y:g}, {request.vector_z:g})",
        )
    return [row]


def _orientation_progress(progress_callback: ProgressCallback | None):
    if progress_callback is None:
        return None

    def on_progress(index, total, orientation) -> None:
        progress_callback(
            index,
            total,
            (
                f"roll={orientation.roll_deg:g}, "
                f"alpha={orientation.alpha_deg:g}, "
                f"beta={orientation.beta_deg:g}"
            ),
        )

    return on_progress


def _range_spec(start: float, end: float, step: float) -> str:
    if step == 0.0:
        raise ValueError("Sweep step must not be zero")
    if start == end:
        return f"{start}"
    return f"{start}:{end}:{step}"
