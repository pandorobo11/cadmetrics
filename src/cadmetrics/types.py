from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from cadmetrics.result_schema import CsvValue, serialize_result_row
from cadmetrics.version import cadmetrics_hash, cadmetrics_version


FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]


@dataclass(frozen=True)
class ModelData:
    """Loaded geometry in output units."""

    path: Path
    source_format: str
    vertices: FloatArray
    faces: IntArray
    input_unit: str
    output_unit: str
    volume: float | None
    surface_area: float | None
    base_area: float | None
    is_watertight: bool | None
    mesh_deflection: float | None = None
    angular_deflection: float | None = None
    base_tolerance: float | None = None
    step_metric_source: str | None = None
    step_component_mode: str | None = None
    newly_exposed_surface_area: float | None = None
    newly_exposed_face_indices: tuple[int, ...] = field(default_factory=tuple)
    is_assembly: bool = False
    component_names: tuple[str, ...] = field(default_factory=tuple)
    selected_components: tuple[int, ...] = field(default_factory=tuple)
    bounds: tuple[float, float, float, float, float, float] | None = None
    load_elapsed_sec: float | None = None
    cadmetrics_version: str = field(default_factory=cadmetrics_version)
    cadmetrics_hash: str = field(default_factory=cadmetrics_hash)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def vertex_count(self) -> int:
        return int(self.vertices.shape[0])

    @property
    def face_count(self) -> int:
        return int(self.faces.shape[0])

    @property
    def x_min(self) -> float | None:
        if self.bounds is not None:
            return self.bounds[0]
        return _axis_min(self.vertices, 0)

    @property
    def x_max(self) -> float | None:
        if self.bounds is not None:
            return self.bounds[1]
        return _axis_max(self.vertices, 0)

    @property
    def y_min(self) -> float | None:
        if self.bounds is not None:
            return self.bounds[2]
        return _axis_min(self.vertices, 1)

    @property
    def y_max(self) -> float | None:
        if self.bounds is not None:
            return self.bounds[3]
        return _axis_max(self.vertices, 1)

    @property
    def z_min(self) -> float | None:
        if self.bounds is not None:
            return self.bounds[4]
        return _axis_min(self.vertices, 2)

    @property
    def z_max(self) -> float | None:
        if self.bounds is not None:
            return self.bounds[5]
        return _axis_max(self.vertices, 2)


@dataclass(frozen=True)
class MeasurementRow:
    file: str
    input_unit: str
    output_unit: str
    roll_deg: float | None
    alpha_deg: float | None
    beta_deg: float | None
    volume: float | None
    surface_area: float | None
    projected_area: float | None
    is_watertight: bool | None
    base_area: float | None = None
    pitch_deg: float | None = None
    direction_x: float | None = None
    direction_y: float | None = None
    direction_z: float | None = None
    centroid_u: float | None = None
    centroid_v: float | None = None
    centroid_x: float | None = None
    centroid_y: float | None = None
    centroid_z: float | None = None
    x_min: float | None = None
    x_max: float | None = None
    y_min: float | None = None
    y_max: float | None = None
    z_min: float | None = None
    z_max: float | None = None
    step_components: tuple[int, ...] = field(default_factory=tuple)
    step_component_names: tuple[str, ...] = field(default_factory=tuple)
    mesh_deflection: float | None = None
    angular_deflection: float | None = None
    base_tolerance: float | None = None
    step_component_mode: str | None = None
    newly_exposed_surface_area: float | None = None
    method: str | None = None
    load_elapsed_sec: float | None = None
    elapsed_sec: float | None = None
    cadmetrics_version: str = field(default_factory=cadmetrics_version)
    cadmetrics_hash: str = field(default_factory=cadmetrics_hash)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_csv_row(self) -> dict[str, CsvValue]:
        return serialize_result_row(self)


def _axis_min(vertices: FloatArray, axis: int) -> float | None:
    if vertices.shape[0] == 0:
        return None
    return float(np.min(vertices[:, axis]))


def _axis_max(vertices: FloatArray, axis: int) -> float | None:
    if vertices.shape[0] == 0:
        return None
    return float(np.max(vertices[:, axis]))
