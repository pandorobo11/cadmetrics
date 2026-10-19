from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from cadmetrics.orientation import (
    Orientation,
    normalize_vector,
    projection_direction_for_orientation,
)
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
        import shapely
    except ImportError as exc:
        raise RuntimeError("Projected area calculation requires the 'shapely' dependency.") from exc

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
    faces = np.asarray(model.faces, dtype=np.int64)
    triangles = projected[faces]

    # A constant u or v coordinate is exactly degenerate, at any scale.
    # Leave other cases to shapely; do not round small positive areas away.
    u = triangles[:, :, 0]
    v = triangles[:, :, 1]
    keep = ~(
        ((u[:, 0] == u[:, 1]) & (u[:, 1] == u[:, 2]))
        | ((v[:, 0] == v[:, 1]) & (v[:, 1] == v[:, 2]))
    )

    if model.is_watertight is True and _is_closed_oriented_surface(vertices, faces):
        # Every line along the projection direction crosses a closed, consistently
        # oriented surface as often front-to-back as back-to-front, so the triangles
        # of either winding sign alone already cover the whole silhouette.
        signed = (u[:, 1] - u[:, 0]) * (v[:, 2] - v[:, 0]) - (u[:, 2] - u[:, 0]) * (
            v[:, 1] - v[:, 0]
        )
        positive = keep & (signed > 0.0)
        negative = keep & (signed < 0.0)
        keep = positive if np.count_nonzero(positive) <= np.count_nonzero(negative) else negative

    if not np.any(keep):
        return ProjectionMetrics(area=0.0, centroid_u=None, centroid_v=None)

    polygons = shapely.polygons(triangles[keep])
    polygons = polygons[shapely.is_valid(polygons) & (shapely.area(polygons) > 0.0)]

    if polygons.size == 0:
        return ProjectionMetrics(area=0.0, centroid_u=None, centroid_v=None)

    outline = _union_polygons(shapely, polygons, projection_direction)
    centroid = outline.centroid
    return ProjectionMetrics(
        area=float(outline.area),
        centroid_u=float(centroid.x),
        centroid_v=float(centroid.y),
    )


# Snap-rounding grid sizes for the retry, relative to the outline's half-extent
# (the largest coordinate once the outline is centred on the origin). Snapping
# moves each vertex by at most half a cell, so the area changes by about
# perimeter * grid: 2**-44 kept the 16-part benchmark assembly within 6e-15
# relative. Grids near one ulp (2**-52) fail again, and the coarser second size
# is a last resort.
_UNION_RETRY_RELATIVE_GRIDS = (2.0**-44, 2.0**-34)


class ProjectionUnionError(RuntimeError):
    """The projected triangles could not be unioned into an outline."""


def _union_polygons(shapely: Any, polygons: np.ndarray, direction: FloatArray) -> Any:
    """Union projected triangles, retrying with snap-rounding when GEOS fails.

    GEOS retries a failed floating-point overlay with snapping and its own
    snap-rounding, but those retries only handle TopologyException. Nearly
    collinear edges, such as sliver triangles whose coordinates differ by one
    ulp, can instead raise "AssertionFailedException: found two shells in
    EdgeRing list" and fail the whole union. Retrying with an explicit tiny
    grid_size runs the snap-rounding overlay on every pairwise union, so only
    the failing directions pay for it and every other result stays
    bit-identical.
    """

    try:
        return shapely.union_all(polygons)
    except shapely.errors.GEOSException as exc:
        first_error = exc

    # Snap in coordinates centred on the outline so the grid follows the
    # outline's size, not its distance from the origin.
    bounds = shapely.total_bounds(polygons)
    center = np.array([(bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0])
    local = shapely.transform(polygons, lambda coords: coords - center)
    scale = float(np.max(np.abs(shapely.total_bounds(local))))
    if not np.isfinite(scale) or scale == 0.0:
        scale = 1.0
    reason = "even with snap-rounding retries"
    for relative_grid in _UNION_RETRY_RELATIVE_GRIDS:
        grid_size = scale * relative_grid
        try:
            outline = shapely.union_all(local, grid_size=grid_size)
        except shapely.errors.GEOSException:
            continue
        # Inputs have positive area. An empty outline means snapping erased all
        # geometry; a coarser grid is not a reliable recovery of that outline.
        if outline.is_empty:
            reason = (
                f"and the snap-rounding retry (grid_size={grid_size!r}) erased the whole outline"
            )
            break
        return shapely.transform(outline, lambda coords: coords + center)

    direction_text = ", ".join(repr(float(value)) for value in direction)
    raise ProjectionUnionError(
        f"Could not union {polygons.size} projected triangles for projection direction "
        f"({direction_text}), {reason}: {first_error}"
    ) from first_error


def _is_closed_oriented_surface(vertices: FloatArray, faces: np.ndarray) -> bool:
    """Return whether every directed edge is matched by its reverse.

    Vertices are welded by exact coordinates first, so per-face triangulations
    that duplicate shared vertices still count. Inconsistently wound faces leave
    unmatched edges and make this False.
    """

    _, welded = np.unique(vertices, axis=0, return_inverse=True)
    welded = welded.reshape(-1).astype(np.int64)
    corners = welded[faces]
    starts = corners.reshape(-1)
    ends = corners[:, [1, 2, 0]].reshape(-1)
    distinct = starts != ends
    starts = starts[distinct]
    ends = ends[distinct]
    if starts.size == 0:
        return False
    vertex_count = int(welded.max()) + 1
    forward = np.sort(starts * vertex_count + ends)
    backward = np.sort(ends * vertex_count + starts)
    return bool(np.array_equal(forward, backward))


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
