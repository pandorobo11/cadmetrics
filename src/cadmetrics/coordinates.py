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

    parsed = (_parse_axis(parts[0]), _parse_axis(parts[1]), _parse_axis(parts[2]))
    source_axes = [axis for axis, _sign in parsed]
    if sorted(source_axes) != [0, 1, 2]:
        raise ValueError("axis_map must use each source axis exactly once")
    return parsed


def transform_model_axes(model: ModelData, axis_map: str) -> ModelData:
    parsed = parse_axis_map(axis_map)
    if parsed == ((0, 1.0), (1, 1.0), (2, 1.0)):
        return model

    vertices, faces = _transform_mesh(model.vertices, model.faces, parsed)
    return replace(
        model,
        vertices=vertices,
        faces=faces,
        component_meshes=tuple(
            _transform_mesh(component_vertices, component_faces, parsed)
            for component_vertices, component_faces in model.component_meshes
        ),
        bounds=_transform_bounds(model.bounds, parsed),
    )


def _transform_mesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    axis_map: tuple[tuple[int, float], ...],
) -> tuple[np.ndarray, np.ndarray]:
    columns = [vertices[:, axis] * sign for axis, sign in axis_map]
    if _axis_map_determinant(axis_map) < 0.0:
        faces = faces[:, [0, 2, 1]]
    return (np.column_stack(columns) if columns else vertices), faces


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


def _transform_bounds(
    bounds: tuple[float, float, float, float, float, float] | None,
    axis_map: tuple[tuple[int, float], ...],
) -> tuple[float, float, float, float, float, float] | None:
    if bounds is None:
        return None
    source_bounds = ((bounds[0], bounds[1]), (bounds[2], bounds[3]), (bounds[4], bounds[5]))
    transformed: list[float] = []
    for source_axis, sign in axis_map:
        lower, upper = source_bounds[source_axis]
        values = (lower * sign, upper * sign)
        transformed.extend([min(values), max(values)])
    return tuple(transformed)  # type: ignore[return-value]
