from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


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
    is_watertight: bool | None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def vertex_count(self) -> int:
        return int(self.vertices.shape[0])

    @property
    def face_count(self) -> int:
        return int(self.faces.shape[0])


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
    pitch_deg: float | None = None
    direction_x: float | None = None
    direction_y: float | None = None
    direction_z: float | None = None
    centroid_u: float | None = None
    centroid_v: float | None = None
    centroid_x: float | None = None
    centroid_y: float | None = None
    centroid_z: float | None = None
    mesh_deflection: float | None = None
    angular_deflection: float | None = None
    method: str | None = None
    elapsed_sec: float | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_csv_row(self) -> dict[str, str | float | bool | None]:
        return {
            "file": self.file,
            "input_unit": self.input_unit,
            "output_unit": self.output_unit,
            "roll_deg": self.roll_deg,
            "pitch_deg": self.pitch_deg,
            "alpha_deg": self.alpha_deg,
            "beta_deg": self.beta_deg,
            "direction_x": self.direction_x,
            "direction_y": self.direction_y,
            "direction_z": self.direction_z,
            "centroid_u": self.centroid_u,
            "centroid_v": self.centroid_v,
            "centroid_x": self.centroid_x,
            "centroid_y": self.centroid_y,
            "centroid_z": self.centroid_z,
            "volume": self.volume,
            "surface_area": self.surface_area,
            "projected_area": self.projected_area,
            "is_watertight": self.is_watertight,
            "mesh_deflection": self.mesh_deflection,
            "angular_deflection": self.angular_deflection,
            "method": self.method,
            "elapsed_sec": self.elapsed_sec,
            "warnings": "; ".join(self.warnings),
        }
