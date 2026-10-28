"""CAD geometry metrics for STL and STEP files."""

from cadmetrics.api import (
    AttitudeMode,
    StepComponentMode,
    inspect_model,
    measure,
    project,
    sections,
    sweep,
)
from cadmetrics.sections import CrossSectionResult, SectionRow, SectionSeries
from cadmetrics.types import MeasurementRow, ModelData
from cadmetrics.version import cadmetrics_hash, cadmetrics_version

__version__ = cadmetrics_version()

__all__ = [
    "CrossSectionResult",
    "MeasurementRow",
    "ModelData",
    "AttitudeMode",
    "StepComponentMode",
    "__version__",
    "cadmetrics_hash",
    "cadmetrics_version",
    "inspect_model",
    "measure",
    "project",
    "SectionRow",
    "SectionSeries",
    "sections",
    "sweep",
]
