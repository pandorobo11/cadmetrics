from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cadmetrics.orientation import Orientation, normalize_vector, projection_direction_for_orientation
from cadmetrics.types import FloatArray, ModelData


@dataclass(frozen=True)
class ProjectionMetrics:
    area: float
    centroid_u: float | None
    centroid_v: float | None


def projected_area(
    model: ModelData,
    *,
    orientation: Orientation | None = None,
    direction: FloatArray | None = None,
) -> float:
    """Calculate orthographic 2D outline area with overlapping triangles unioned."""

    return projected_metrics(model, orientation=orientation, direction=direction).area


def projected_metrics(
    model: ModelData,
    *,
    orientation: Orientation | None = None,
    direction: FloatArray | None = None,
) -> ProjectionMetrics:
    """Calculate orthographic 2D outline area and its projected centroid."""

    try:
        from shapely.geometry import Polygon
    except ImportError as exc:
        raise RuntimeError("Projected area calculation requires the 'shapely' dependency.") from exc
    try:
        from shapely import union_all
    except ImportError:
        from shapely.ops import unary_union as union_all

    if model.face_count == 0:
        return ProjectionMetrics(area=0.0, centroid_u=None, centroid_v=None)

    vertices = model.vertices
    projection_direction = np.array([1.0, 0.0, 0.0], dtype=float)

    if orientation is not None:
        projection_direction = projection_direction_for_orientation(orientation)

    if direction is not None:
        projection_direction = normalize_vector(direction)

    basis_u, basis_v = projection_basis(projection_direction)
    projected = np.column_stack((vertices @ basis_u, vertices @ basis_v))

    polygons = []
    for face in model.faces:
        polygon = Polygon(projected[face])
        if polygon.is_valid and polygon.area > 0.0:
            polygons.append(polygon)

    if not polygons:
        return ProjectionMetrics(area=0.0, centroid_u=None, centroid_v=None)

    outline = union_all(polygons)
    centroid = outline.centroid
    return ProjectionMetrics(
        area=float(outline.area),
        centroid_u=float(centroid.x),
        centroid_v=float(centroid.y),
    )


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
