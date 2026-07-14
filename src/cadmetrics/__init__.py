"""CAD geometry metrics for STL and STEP files."""

from cadmetrics.api import AttitudeMode, inspect_model, measure, project, sweep
from cadmetrics.types import MeasurementRow, ModelData
from cadmetrics.version import cadmetrics_hash, cadmetrics_version

__version__ = cadmetrics_version()

__all__ = [
    "MeasurementRow",
    "ModelData",
    "AttitudeMode",
    "__version__",
    "cadmetrics_hash",
    "cadmetrics_version",
    "inspect_model",
    "measure",
    "project",
    "sweep",
]
