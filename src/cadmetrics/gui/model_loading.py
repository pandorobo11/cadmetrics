from __future__ import annotations

from cadmetrics.api import _inspect_model_with_options
from cadmetrics.gui.gui_types import ModelLoadKey
from cadmetrics.gui.jobs import CalculationRequest
from cadmetrics.types import ModelData


def load_model_for_request(request: CalculationRequest) -> ModelData:
    return _inspect_model_with_options(request.file, request.load_options())


def model_load_key(request: CalculationRequest) -> ModelLoadKey:
    return ModelLoadKey.from_request(request)
