from __future__ import annotations

from dataclasses import dataclass, replace
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
from cadmetrics.sections import (
    DEFAULT_SECTION_COUNT,
    DEFAULT_THETA_COUNT,
    CrossSectionResult,
    calculate_sections,
    validate_section_options,
)
from cadmetrics.sweep import SweepRange
from cadmetrics.types import MeasurementRow, ModelData

AnalysisMode = Literal["projection", "sections"]
AttitudeInputMode = Literal["alpha_beta", "roll_pitch", "vector"]
ProgressCallback = Callable[[int, int, str], None]
RowCallback = Callable[[MeasurementRow], None]
OrientationProgressCallback = Callable[[int, int, MeasurementRow], None]
GuiModelPath = Path | tuple[Path, ...]


@dataclass(frozen=True)
class CalculationRequest:
    file: GuiModelPath
    attitude_mode: AttitudeInputMode = "alpha_beta"
    input_unit: str = "auto"
    output_unit: str = "m"
    mesh_deflection: float | str = "auto"
    angular_deflection: float | str = "auto"
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
    analysis: AnalysisMode = "projection"
    section_count: int = DEFAULT_SECTION_COUNT
    mach: float = 1.0
    theta_count: int = DEFAULT_THETA_COUNT
    symmetric: bool = False
    # Freestream direction the sections are cut relative to.
    section_alpha: float = 0.0
    section_beta: float = 0.0

    def projection_inputs(self) -> CalculationRequest:
        """This request with only the inputs that change projected-area results."""
        return replace(
            self,
            analysis="projection",
            section_count=DEFAULT_SECTION_COUNT,
            mach=1.0,
            theta_count=DEFAULT_THETA_COUNT,
            symmetric=False,
            section_alpha=0.0,
            section_beta=0.0,
        )

    def section_inputs(self) -> CalculationRequest:
        """This request with only the inputs that change cross-section results."""
        defaults = CalculationRequest(file=self.file)
        attitude_fields = {
            name: getattr(defaults, name)
            for name in (
                "attitude_mode",
                "roll_start",
                "roll_end",
                "roll_step",
                "alpha_start",
                "alpha_end",
                "alpha_step",
                "beta_start",
                "beta_end",
                "beta_step",
                "pitch_start",
                "pitch_end",
                "pitch_step",
                "vector_x",
                "vector_y",
                "vector_z",
            )
        }
        # Roll angles only matter for Mach planes.
        supersonic = self.mach > 1.0
        return replace(
            self,
            analysis="sections",
            theta_count=self.theta_count if supersonic else DEFAULT_THETA_COUNT,
            symmetric=self.symmetric if supersonic else False,
            **attitude_fields,
        )

    def validate(self) -> None:
        """Raise ValueError when the analysis inputs cannot be calculated."""
        if self.analysis == "sections":
            validate_section_options(
                section_count=self.section_count,
                mach=self.mach,
                theta_count=self.theta_count,
                symmetric=self.symmetric,
                alpha_deg=self.section_alpha,
                beta_deg=self.section_beta,
            )
        else:
            self.resolved_attitude()

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
            component_preview_meshes=True,
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
    row_callback: RowCallback | None = None,
) -> list[MeasurementRow]:
    """Run one GUI request; ``row_callback`` receives each row as soon as it is computed."""
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
        if row_callback is not None:
            row_callback(row)
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
            progress_callback=_orientation_progress(progress_callback, row_callback, "roll_pitch"),
            cancel_callback=cancel_callback,
        )
    return sweep_model(
        model,
        attitude="alpha-beta",
        alpha_deg=attitude.alpha,
        beta_deg=attitude.beta,
        progress_callback=_orientation_progress(progress_callback, row_callback, "alpha_beta"),
        cancel_callback=cancel_callback,
    )


def run_sections(
    request: CalculationRequest,
    *,
    model: ModelData | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> CrossSectionResult:
    """Run one GUI cross-section request on a loaded (or newly loaded) model."""
    if model is None:
        model = _inspect_model_with_options(request.file, request.load_options())

    def on_progress(done: int, total: int) -> None:
        if progress_callback is not None:
            progress_callback(done, total, "sections")

    return calculate_sections(
        model,
        section_count=request.section_count,
        mach=request.mach,
        theta_count=request.theta_count,
        symmetric=request.symmetric,
        alpha_deg=request.section_alpha,
        beta_deg=request.section_beta,
        progress_callback=on_progress,
        cancel_callback=cancel_callback,
    )


def _orientation_progress(
    progress_callback: ProgressCallback | None,
    row_callback: RowCallback | None,
    mode: Literal["alpha_beta", "roll_pitch"],
) -> OrientationProgressCallback | None:
    if progress_callback is None and row_callback is None:
        return None

    def on_progress(index: int, total: int, row: MeasurementRow) -> None:
        if row_callback is not None:
            row_callback(row)
        if progress_callback is None:
            return
        if mode == "roll_pitch":
            text = f"roll={row.roll_deg:g}, pitch={row.pitch_deg:g}"
        else:
            text = f"alpha={row.alpha_deg:g}, beta={row.beta_deg:g}"
        progress_callback(index, total, text)

    return on_progress
