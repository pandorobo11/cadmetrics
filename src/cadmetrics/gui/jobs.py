from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from cadmetrics.api import StepComponentMode, project, project_model, sweep, sweep_model
from cadmetrics.coordinates import DEFAULT_AXIS_MAP
from cadmetrics.io import DEFAULT_BASE_TOLERANCE
from cadmetrics.types import MeasurementRow, ModelData

AttitudeInputMode = Literal["alpha_beta", "roll_pitch", "vector"]
ProgressCallback = Callable[[int, int, str], None]
GuiModelPath = Path | tuple[Path, ...]


@dataclass(frozen=True)
class CalculationRequest:
    file: GuiModelPath
    attitude_mode: AttitudeInputMode = "alpha_beta"
    input_unit: str = "auto"
    output_unit: str = "m"
    mesh_deflection: float | str = "auto"
    angular_deflection: float = 0.1
    base_tolerance: float = DEFAULT_BASE_TOLERANCE
    axis_map: str = DEFAULT_AXIS_MAP
    step_metric_source: str = "brep"
    step_components: tuple[int, ...] | None = None
    step_component_mode: StepComponentMode = "filter"
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
    model: ModelData | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[MeasurementRow]:
    common = {
        "input_unit": request.input_unit,
        "output_unit": request.output_unit,
        "mesh_deflection": request.mesh_deflection,
        "angular_deflection": request.angular_deflection,
        "base_tolerance": request.base_tolerance,
        "axis_map": request.axis_map,
        "step_metric_source": request.step_metric_source,
        "step_components": request.step_components,
        "step_component_mode": request.step_component_mode,
    }
    if request.attitude_mode == "alpha_beta":
        if model is not None:
            return sweep_model(
                model,
                attitude="alpha-beta",
                alpha_deg=_range_spec(request.alpha_start, request.alpha_end, request.alpha_step),
                beta_deg=_range_spec(request.beta_start, request.beta_end, request.beta_step),
                progress_callback=_orientation_progress(progress_callback, "alpha_beta"),
            )
        return sweep(
            request.file,
            attitude="alpha-beta",
            alpha_deg=_range_spec(request.alpha_start, request.alpha_end, request.alpha_step),
            beta_deg=_range_spec(request.beta_start, request.beta_end, request.beta_step),
            progress_callback=_orientation_progress(progress_callback, "alpha_beta"),
            **common,
        )
    if request.attitude_mode == "roll_pitch":
        if model is not None:
            return sweep_model(
                model,
                attitude="roll-pitch",
                roll_deg=_range_spec(request.roll_start, request.roll_end, request.roll_step),
                pitch_deg=_range_spec(request.pitch_start, request.pitch_end, request.pitch_step),
                progress_callback=_orientation_progress(progress_callback, "roll_pitch"),
            )
        return sweep(
            request.file,
            attitude="roll-pitch",
            roll_deg=_range_spec(request.roll_start, request.roll_end, request.roll_step),
            pitch_deg=_range_spec(request.pitch_start, request.pitch_end, request.pitch_step),
            progress_callback=_orientation_progress(progress_callback, "roll_pitch"),
            **common,
        )

    direction = f"{request.vector_x},{request.vector_y},{request.vector_z}"
    if model is not None:
        row = project_model(model, attitude="vector", direction=direction)
    else:
        row = project(
            request.file,
            attitude="vector",
            direction=direction,
            **common,
        )
    if progress_callback is not None:
        progress_callback(
            1,
            1,
            f"vector=({request.vector_x:g}, {request.vector_y:g}, {request.vector_z:g})",
        )
    return [row]


def _orientation_progress(
    progress_callback: ProgressCallback | None,
    mode: Literal["alpha_beta", "roll_pitch"],
):
    if progress_callback is None:
        return None

    def on_progress(index, total, row) -> None:
        if mode == "roll_pitch":
            text = f"roll={row.roll_deg:g}, pitch={row.pitch_deg:g}"
        else:
            text = f"alpha={row.alpha_deg:g}, beta={row.beta_deg:g}"
        progress_callback(index, total, text)

    return on_progress


def _range_spec(start: float, end: float, step: float) -> str:
    if step == 0.0:
        raise ValueError("Sweep step must not be zero")
    if start == end:
        return f"{start}"
    return f"{start}:{end}:{step}"
