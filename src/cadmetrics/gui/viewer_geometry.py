from __future__ import annotations

from typing import Any

import numpy as np

from cadmetrics.io import DEFAULT_BASE_TOLERANCE
from cadmetrics.projection import projection_basis
from cadmetrics.types import MeasurementRow, ModelData


def row_centroid_point(row: MeasurementRow | None) -> np.ndarray | None:
    if row is None or row.centroid_x is None or row.centroid_y is None or row.centroid_z is None:
        return None
    return np.array([row.centroid_x, row.centroid_y, row.centroid_z], dtype=float)


def projection_arrow_geometry(
    vertices: np.ndarray,
    direction: np.ndarray,
    *,
    through_point: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    anchor = vertices.mean(axis=0) if through_point is None else through_point
    unit_direction = direction / np.linalg.norm(direction)
    spans = np.ptp(vertices, axis=0)
    scale = max(float(spans.max()), 1.0)
    clearance = scale * 0.15
    projections = (vertices - anchor) @ unit_direction
    upstream_edge = float(projections.min())
    arrow_length = scale * 0.35
    start = anchor + unit_direction * (upstream_edge - clearance - arrow_length)
    vector = unit_direction * arrow_length
    return start, vector


def base_face_mask(
    vertices: np.ndarray,
    faces: np.ndarray,
    relative_tolerance: float,
) -> np.ndarray:
    if vertices.size == 0 or faces.size == 0:
        return np.zeros(faces.shape[0], dtype=bool)
    diagonal = float(np.linalg.norm(np.ptp(vertices, axis=0)))
    tolerance = max(diagonal * relative_tolerance, 1.0e-12)
    xmax = float(np.max(vertices[:, 0]))
    return np.all(np.abs(vertices[faces, 0] - xmax) <= tolerance, axis=1)


def base_face_polydata(model: ModelData, pv: Any) -> Any | None:
    relative_tolerance = model.base_tolerance or DEFAULT_BASE_TOLERANCE
    mask = base_face_mask(model.vertices, model.faces, relative_tolerance)
    if not bool(np.any(mask)):
        return None

    triangles = model.vertices[model.faces[mask]].copy()
    diagonal = float(np.linalg.norm(np.ptp(model.vertices, axis=0)))
    triangles[:, :, 0] += max(diagonal * 1.0e-5, 1.0e-12)
    highlight_vertices = triangles.reshape(-1, 3)
    highlight_faces = np.column_stack(
        [
            np.full(triangles.shape[0], 3, dtype=np.int64),
            np.arange(highlight_vertices.shape[0], dtype=np.int64).reshape(-1, 3),
        ]
    ).ravel()
    return pv.PolyData(highlight_vertices, highlight_faces)


def projection_camera_geometry(
    vertices: np.ndarray,
    direction: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = vertices.mean(axis=0)
    unit_direction = direction / np.linalg.norm(direction)
    spans = np.ptp(vertices, axis=0)
    scale = max(float(spans.max()), 1.0)
    distance = scale * 3.0
    _, view_up = projection_basis(unit_direction)
    position = center - unit_direction * distance
    return position, center, view_up


def default_camera_geometry(vertices: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return camera_geometry(vertices, np.array([-1.0, -1.0, 1.0], dtype=float))


def camera_geometry(
    vertices: np.ndarray,
    from_direction: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = vertices.mean(axis=0)
    from_direction = from_direction / np.linalg.norm(from_direction)
    spans = np.ptp(vertices, axis=0)
    scale = max(float(spans.max()), 1.0)
    distance = scale * 3.0
    position = center + from_direction * distance
    view_direction = (center - position) / np.linalg.norm(center - position)
    up_hint = (
        np.array([0.0, 1.0, 0.0], dtype=float)
        if abs(float(view_direction[2])) > 0.9
        else np.array([0.0, 0.0, 1.0], dtype=float)
    )
    view_up = up_hint - view_direction * float(np.dot(up_hint, view_direction))
    view_up = view_up / np.linalg.norm(view_up)
    return position, center, view_up
