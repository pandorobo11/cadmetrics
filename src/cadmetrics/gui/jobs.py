from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from cadmetrics.api import _inspect_model_with_options, project_model, sweep_model
from cadmetrics.attitude import ResolvedSweepAttitude, resolve_sweep_attitude
from cadmetrics.coordinates import DEFAULT_AXIS_MAP
from cadmetrics.load_options import (
    DEFAULT_BASE_TOLERANCE,
    ModelLoadOptions,
    StepComponentMode,
)
from cadmetrics.sweep import SweepRange
from cadmetrics.types import MeasurementRow, ModelData

AttitudeInputMode = Literal["alpha_beta", "roll_pitch", "vector"]
ProgressCallback = Callable[[int, int, str], None]
OrientationProgressCallback = Callable[[int, int, MeasurementRow], None]
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

    def load_options(self) -> ModelLoadOptions:
        return ModelLoadOptions.resolve(
            input_unit=self.input_unit,
            output_unit=self.output_unit,
            mesh_deflection=self.mesh_deflection,
            angular_deflection=self.angular_deflection,
            base_tolerance=self.base_tolerance,
            axis_map=self.axis_map,
            step_metric_source=self.step_metric_source,
            step_components=self.step_components,
            step_component_mode=self.step_component_mode,
        )

    def resolved_attitude(self) -> ResolvedSweepAttitude:
        if self.attitude_mode == "vector":
            return resolve_sweep_attitude(
                attitude="vector",
                direction=f"{self.vector_x},{self.vector_y},{self.vector_z}",
            )
        if self.attitude_mode == "roll_pitch":
            return resolve_sweep_attitude(
                attitude="roll-pitch",
                roll_deg=SweepRange(self.roll_start, self.roll_end, self.roll_step).spec,
                pitch_deg=SweepRange(self.pitch_start, self.pitch_end, self.pitch_step).spec,
            )
        return resolve_sweep_attitude(
            attitude="alpha-beta",
            alpha_deg=SweepRange(self.alpha_start, self.alpha_end, self.alpha_step).spec,
            beta_deg=SweepRange(self.beta_start, self.beta_end, self.beta_step).spec,
        )


def run_calculation(
    request: CalculationRequest,
    *,
    model: ModelData | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> list[MeasurementRow]:
    attitude = request.resolved_attitude()
    if model is None:
        model = _inspect_model_with_options(request.file, request.load_options())
    if attitude.mode == "vector":
        if cancel_callback is not None:
            cancel_callback()
        assert attitude.direction is not None
        row = project_model(model, attitude="vector", direction=attitude.direction)
        if cancel_callback is not None:
            cancel_callback()
        if progress_callback is not None:
            progress_callback(
                1,
                1,
                f"vector=({request.vector_x:g}, {request.vector_y:g}, {request.vector_z:g})",
            )
        return [row]

    if attitude.mode == "roll-pitch":
        return sweep_model(
            model,
            attitude="roll-pitch",
            roll_deg=attitude.roll,
            pitch_deg=attitude.alpha,
            progress_callback=_orientation_progress(progress_callback, "roll_pitch"),
            cancel_callback=cancel_callback,
        )
    return sweep_model(
        model,
        attitude="alpha-beta",
        alpha_deg=attitude.alpha,
        beta_deg=attitude.beta,
        progress_callback=_orientation_progress(progress_callback, "alpha_beta"),
        cancel_callback=cancel_callback,
    )


def _orientation_progress(
    progress_callback: ProgressCallback | None,
    mode: Literal["alpha_beta", "roll_pitch"],
) -> OrientationProgressCallback | None:
    if progress_callback is None:
        return None

    def on_progress(index: int, total: int, row: MeasurementRow) -> None:
        if mode == "roll_pitch":
            text = f"roll={row.roll_deg:g}, pitch={row.pitch_deg:g}"
        else:
            text = f"alpha={row.alpha_deg:g}, beta={row.beta_deg:g}"
        progress_callback(index, total, text)

    return on_progress
