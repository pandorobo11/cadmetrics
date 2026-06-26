from __future__ import annotations

import numpy as np

from cadmetrics.orientation import Orientation, normalize_vector, rotation_matrix
from cadmetrics.types import FloatArray, ModelData


def projected_area(
    model: ModelData,
    *,
    orientation: Orientation | None = None,
    direction: FloatArray | None = None,
) -> float:
    """Calculate orthographic 2D outline area with overlapping triangles unioned."""

    try:
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
    except ImportError as exc:
        raise RuntimeError("Projected area calculation requires the 'shapely' dependency.") from exc

    if model.face_count == 0:
        return 0.0

    vertices = model.vertices
    projection_direction = np.array([1.0, 0.0, 0.0], dtype=float)

    if orientation is not None:
        matrix = rotation_matrix(orientation)
        vertices = vertices @ matrix.T

    if direction is not None:
        projection_direction = normalize_vector(direction)

    basis_u, basis_v = projection_basis(projection_direction)
    projected = np.column_stack((vertices @ basis_u, vertices @ basis_v))

    polygons = []
    for face in model.faces:
        coords = projected[face]
        if _triangle_area(coords) <= 1.0e-15:
            continue
        polygon = Polygon(coords)
        if polygon.is_valid and polygon.area > 0.0:
            polygons.append(polygon)

    if not polygons:
        return 0.0

    return float(unary_union(polygons).area)


def projection_basis(direction: FloatArray) -> tuple[FloatArray, FloatArray]:
    normal = normalize_vector(direction)
    helper = np.array([0.0, 0.0, 1.0], dtype=float)
    if abs(float(np.dot(normal, helper))) > 0.95:
        helper = np.array([0.0, 1.0, 0.0], dtype=float)

    basis_u = np.cross(helper, normal)
    basis_u = normalize_vector(basis_u)
    basis_v = np.cross(normal, basis_u)
    basis_v = normalize_vector(basis_v)
    return basis_u, basis_v


def _triangle_area(coords: FloatArray) -> float:
    a = coords[1] - coords[0]
    b = coords[2] - coords[0]
    return abs(float(a[0] * b[1] - a[1] * b[0])) * 0.5
