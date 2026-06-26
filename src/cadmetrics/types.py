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
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_csv_row(self) -> dict[str, str | float | bool | None]:
        return {
            "file": self.file,
            "input_unit": self.input_unit,
            "output_unit": self.output_unit,
            "roll_deg": self.roll_deg,
            "alpha_deg": self.alpha_deg,
            "beta_deg": self.beta_deg,
            "volume": self.volume,
            "surface_area": self.surface_area,
            "projected_area": self.projected_area,
            "is_watertight": self.is_watertight,
            "warnings": "; ".join(self.warnings),
        }
