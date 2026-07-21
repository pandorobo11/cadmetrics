from __future__ import annotations

from cadmetrics.api import inspect_model
from cadmetrics.gui.gui_types import ModelLoadKey
from cadmetrics.gui.jobs import CalculationRequest
from cadmetrics.types import ModelData


def load_model_for_request(request: CalculationRequest) -> ModelData:
    return inspect_model(
        request.file,
        input_unit=request.input_unit,
        output_unit=request.output_unit,
        mesh_deflection=request.mesh_deflection,
        angular_deflection=request.angular_deflection,
        base_tolerance=request.base_tolerance,
        step_metric_source=request.step_metric_source,
        axis_map=request.axis_map,
        step_components=request.step_components,
        step_component_mode=request.step_component_mode,
    )


def model_load_key(request: CalculationRequest) -> ModelLoadKey:
    return ModelLoadKey.from_request(request)
