from __future__ import annotations

from dataclasses import replace

import numpy as np

from cadmetrics.types import ModelData

AXIS_CHOICES = ("x", "-x", "y", "-y", "z", "-z")
DEFAULT_AXIS_MAP = "x,y,z"


def parse_axis_map(value: str) -> tuple[tuple[int, float], tuple[int, float], tuple[int, float]]:
    parts = [part.strip().lower().lstrip("+") for part in value.split(",")]
    if len(parts) != 3:
        raise ValueError("axis_map must contain three comma-separated axes, e.g. x,y,z")

    parsed = tuple(_parse_axis(part) for part in parts)
    source_axes = [axis for axis, _sign in parsed]
    if sorted(source_axes) != [0, 1, 2]:
        raise ValueError("axis_map must use each source axis exactly once")
    return parsed


def transform_model_axes(model: ModelData, axis_map: str) -> ModelData:
    parsed = parse_axis_map(axis_map)
    if parsed == ((0, 1.0), (1, 1.0), (2, 1.0)):
        return model

    columns = [model.vertices[:, axis] * sign for axis, sign in parsed]
    faces = model.faces
    if _axis_map_determinant(parsed) < 0.0:
        faces = faces[:, [0, 2, 1]]
    return replace(model, vertices=np.column_stack(columns), faces=faces)


def _parse_axis(value: str) -> tuple[int, float]:
    sign = -1.0 if value.startswith("-") else 1.0
    axis_name = value[1:] if value.startswith("-") else value
    axis_lookup = {"x": 0, "y": 1, "z": 2}
    if axis_name not in axis_lookup:
        raise ValueError(f"Invalid axis '{value}'. Use one of: {', '.join(AXIS_CHOICES)}")
    return axis_lookup[axis_name], sign


def _axis_map_determinant(axis_map: tuple[tuple[int, float], ...]) -> float:
    matrix = np.zeros((3, 3), dtype=float)
    for output_axis, (input_axis, sign) in enumerate(axis_map):
        matrix[output_axis, input_axis] = sign
    return float(np.linalg.det(matrix))
