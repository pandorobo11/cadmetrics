from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from cadmetrics.gui.jobs import CalculationRequest
from cadmetrics.load_options import ModelLoadOptions


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
    show_centroid: bool = True
    show_base_face: bool = False
    show_newly_exposed_surface: bool = True
    show_overlay: bool = True
    detailed_overlay: bool = False
    camera_direction: tuple[float, float, float] = (-1.0, -1.0, 1.0)


@dataclass(frozen=True)
class ModelLoadKey:
    files: tuple[Path, ...]
    options: ModelLoadOptions

    @classmethod
    def from_request(cls, request: CalculationRequest) -> ModelLoadKey:
        raw_files = request.file if isinstance(request.file, tuple) else (request.file,)
        return cls(
            files=tuple(Path(path).expanduser().resolve() for path in raw_files),
            options=request.load_options(),
        )
