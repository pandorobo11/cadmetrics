from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

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
    elapsed_sec: float | None = None
    cadmetrics_version: str = field(default_factory=cadmetrics_version)
    cadmetrics_hash: str = field(default_factory=cadmetrics_hash)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_csv_row(self) -> dict[str, str | float | bool | None]:
        return {
            "file": self.file,
            "step_components": ",".join(str(index) for index in self.step_components),
            "step_component_names": "; ".join(self.step_component_names),
            "input_unit": self.input_unit,
            "output_unit": self.output_unit,
            "roll_deg": self.roll_deg,
            "pitch_deg": self.pitch_deg,
            "alpha_deg": self.alpha_deg,
            "beta_deg": self.beta_deg,
            "direction_x": self.direction_x,
            "direction_y": self.direction_y,
            "direction_z": self.direction_z,
            "x_min": self.x_min,
            "x_max": self.x_max,
            "y_min": self.y_min,
            "y_max": self.y_max,
            "z_min": self.z_min,
            "z_max": self.z_max,
            "surface_area": self.surface_area,
            "newly_exposed_surface_area": self.newly_exposed_surface_area,
            "base_area": self.base_area,
            "volume": self.volume,
            "projected_area": self.projected_area,
            "centroid_u": self.centroid_u,
            "centroid_v": self.centroid_v,
            "centroid_x": self.centroid_x,
            "centroid_y": self.centroid_y,
            "centroid_z": self.centroid_z,
            "is_watertight": self.is_watertight,
            "mesh_deflection": self.mesh_deflection,
            "angular_deflection": self.angular_deflection,
            "base_tolerance": self.base_tolerance,
            "step_component_mode": self.step_component_mode,
            "method": self.method,
            "elapsed_sec": self.elapsed_sec,
            "cadmetrics_version": self.cadmetrics_version,
            "cadmetrics_hash": self.cadmetrics_hash,
            "warnings": "; ".join(self.warnings),
        }


def _axis_min(vertices: FloatArray, axis: int) -> float | None:
    if vertices.shape[0] == 0:
        return None
    return float(np.min(vertices[:, axis]))


def _axis_max(vertices: FloatArray, axis: int) -> float | None:
    if vertices.shape[0] == 0:
        return None
    return float(np.max(vertices[:, axis]))
