from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from cadmetrics.gui.jobs import CalculationRequest


class OperationState(StrEnum):
    IDLE = "idle"
    LOADING = "loading"
    CALCULATING = "calculating"
    CANCELLING = "cancelling"


@dataclass(frozen=True)
class ViewerOptions:
    transparent_shape: bool = False
    mesh_edges: bool = False
    feature_edges: bool = True
    show_projection_arrow: bool = True
    show_base_face: bool = False
    show_newly_exposed_surface: bool = True
    show_overlay: bool = True
    camera_direction: tuple[float, float, float] = (-1.0, -1.0, 1.0)


@dataclass(frozen=True)
class ModelLoadKey:
    files: tuple[Path, ...]
    input_unit: str
    output_unit: str
    mesh_deflection: float | str
    angular_deflection: float
    base_tolerance: float
    axis_map: str
    step_metric_source: str
    step_components: tuple[int, ...] | None
    step_component_mode: str

    @classmethod
    def from_request(cls, request: CalculationRequest) -> ModelLoadKey:
        raw_files = request.file if isinstance(request.file, tuple) else (request.file,)
        return cls(
            files=tuple(Path(path).expanduser().resolve() for path in raw_files),
            input_unit=request.input_unit,
            output_unit=request.output_unit,
            mesh_deflection=request.mesh_deflection,
            angular_deflection=request.angular_deflection,
            base_tolerance=request.base_tolerance,
            axis_map=request.axis_map,
            step_metric_source=request.step_metric_source,
            step_components=request.step_components,
            step_component_mode=request.step_component_mode,
        )
