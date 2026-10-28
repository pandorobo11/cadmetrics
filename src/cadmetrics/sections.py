"""Cross-sectional area distributions for area-rule studies.

Sections are cut through the triangle mesh by planes ``x - beta * (y cos(theta) +
z sin(theta)) = x0`` with ``beta = sqrt(M^2 - 1)``. At Mach 1 these are the planes normal
to the X axis (Whitcomb's transonic area rule). Above Mach 1 they are the Mach planes of
Jones' supersonic area rule, and each roll angle theta gives one equivalent body. Every
section area is measured after projecting the cut onto the YZ plane, which is the area
the supersonic area rule uses, and ``x0`` is where the plane crosses the X axis
(Y = Z = 0).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cadmetrics.result_schema import CsvValue, serialize_section_row
from cadmetrics.types import FloatArray, IntArray, ModelData
from cadmetrics.version import cadmetrics_hash, cadmetrics_version

DEFAULT_SECTION_COUNT = 101
MIN_SECTION_COUNT = 5
MAX_SECTION_COUNT = 2001
DEFAULT_THETA_COUNT = 16
MAX_THETA_COUNT = 72
MAX_MACH = 10.0

# Snap-rounding grid for a section whose noded outline GEOS cannot build, relative to the
# section's half-extent; see projection._UNION_RETRY_RELATIVE_GRIDS.
_NODING_RETRY_RELATIVE_GRID = 2.0**-40
# Winding numbers are evaluated for this many arrangement faces at a time.
_WINDING_CHUNK = 256


@dataclass(frozen=True)
class SectionMesh:
    """A model mesh prepared for slicing.

    Vertices are welded by exact coordinates so that per-face STEP triangulations share
    their edges, and faces that repeat a vertex are dropped. ``face_edges[:, j]`` is the
    edge from ``faces[:, j]`` to ``faces[:, (j + 1) % 3]``; ``edges`` holds each edge's
    vertices with the smaller index first, so a crossing point computed from either
    neighbouring face is bit-identical.
    """

    vertices: FloatArray
    faces: IntArray
    edges: IntArray
    face_edges: IntArray
    closed_oriented: bool
    # +1 for outward-facing triangles, -1 for an inside-out closed mesh.
    orientation: float


@dataclass(frozen=True)
class SectionSeries:
    """The section-area distribution of one equivalent body (one roll angle)."""

    theta_deg: float | None
    weight: float
    x: FloatArray
    area: FloatArray
    # True where the plane crossed a hole in the mesh.
    open_flags: NDArray[np.bool_]
    elapsed_sec: float

    @property
    def open_sections(self) -> int:
        return int(np.count_nonzero(self.open_flags))

    @property
    def length(self) -> float:
        return float(self.x[-1] - self.x[0])

    @property
    def volume(self) -> float:
        """Integral of the area over x; equals the model volume for a closed model."""

        return float(np.trapezoid(self.area, self.x))

    @property
    def max_area(self) -> float:
        return float(np.max(self.area))

    @property
    def max_area_x(self) -> float:
        return float(self.x[int(np.argmax(self.area))])

    @property
    def area_slope(self) -> FloatArray:
        return np.gradient(self.area, self.x) if self.length > 0.0 else np.zeros_like(self.area)

    @property
    def wave_drag_area(self) -> float | None:
        return wave_drag_area(self.x, self.area)

    @property
    def sears_haack_area(self) -> FloatArray:
        return sears_haack_area(self.x, volume=self.volume)

    @property
    def sears_haack_drag_area(self) -> float | None:
        return sears_haack_drag_area(length=self.length, volume=self.volume)


@dataclass(frozen=True)
class SectionRow:
    """One cutting plane of a cross-section calculation, as written to CSV."""

    file: str
    input_unit: str
    output_unit: str
    mach: float
    theta_deg: float | None
    theta_weight: float
    station: int
    x: float
    area: float
    area_slope: float
    sears_haack_area: float
    wave_drag_area: float | None
    sears_haack_drag_area: float | None
    mean_wave_drag_area: float | None
    open_section: bool
    step_components: tuple[int, ...] = field(default_factory=tuple)
    step_component_names: tuple[str, ...] = field(default_factory=tuple)
    mesh_deflection: float | None = None
    angular_deflection: float | None = None
    step_component_mode: str | None = None
    method: str | None = None
    cadmetrics_version: str = field(default_factory=cadmetrics_version)
    cadmetrics_hash: str = field(default_factory=cadmetrics_hash)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_csv_row(self) -> dict[str, CsvValue]:
        return serialize_section_row(self)


@dataclass(frozen=True)
class CrossSectionResult:
    """Cross-section distributions for every roll angle of one calculation."""

    model: ModelData
    mach: float
    section_count: int
    theta_count: int
    symmetric: bool
    series: tuple[SectionSeries, ...]
    warnings: tuple[str, ...]
    elapsed_sec: float

    @property
    def wave_drag_area(self) -> float | None:
        """Wave drag D/q averaged over the roll angles, in output_unit^2."""

        return _weighted_mean([(s.weight, s.wave_drag_area) for s in self.series])

    @property
    def sears_haack_drag_area(self) -> float | None:
        """D/q of the Sears-Haack bodies with each equivalent body's length and volume."""

        return _weighted_mean([(s.weight, s.sears_haack_drag_area) for s in self.series])

    @property
    def max_area(self) -> float:
        return max(s.max_area for s in self.series)

    def rows(self) -> list[SectionRow]:
        model = self.model
        warnings = tuple(dict.fromkeys((*model.warnings, *self.warnings)))
        mean_drag = self.wave_drag_area
        names = tuple(
            model.component_names[index - 1]
            for index in model.selected_components
            if 1 <= index <= len(model.component_names)
        )
        rows: list[SectionRow] = []
        for series in self.series:
            slope = series.area_slope
            sears_haack = series.sears_haack_area
            drag = series.wave_drag_area
            sears_haack_drag = series.sears_haack_drag_area
            for index, (x, area) in enumerate(zip(series.x, series.area, strict=True)):
                rows.append(
                    SectionRow(
                        file=str(model.path),
                        input_unit=model.input_unit,
                        output_unit=model.output_unit,
                        mach=self.mach,
                        theta_deg=series.theta_deg,
                        theta_weight=series.weight,
                        station=index + 1,
                        x=float(x),
                        area=float(area),
                        area_slope=float(slope[index]),
                        sears_haack_area=float(sears_haack[index]),
                        wave_drag_area=drag,
                        sears_haack_drag_area=sears_haack_drag,
                        mean_wave_drag_area=mean_drag,
                        open_section=bool(series.open_flags[index]),
                        step_components=model.selected_components,
                        step_component_names=names,
                        mesh_deflection=model.mesh_deflection,
                        angular_deflection=model.angular_deflection,
                        step_component_mode=model.step_component_mode,
                        method=_method_name(model),
                        cadmetrics_version=model.cadmetrics_version,
                        cadmetrics_hash=model.cadmetrics_hash,
                        warnings=warnings,
                    )
                )
        return rows


def validate_section_options(
    *, section_count: int, mach: float, theta_count: int, symmetric: bool
) -> None:
    if not MIN_SECTION_COUNT <= section_count <= MAX_SECTION_COUNT:
        raise ValueError(
            f"sections must be between {MIN_SECTION_COUNT} and {MAX_SECTION_COUNT}, "
            f"got {section_count}."
        )
    if not math.isfinite(mach) or not 1.0 <= mach <= MAX_MACH:
        raise ValueError(f"Mach number must be between 1 and {MAX_MACH:g}, got {mach!r}.")
    if mach > 1.0:
        if not 1 <= theta_count <= MAX_THETA_COUNT:
            raise ValueError(
                f"theta count must be between 1 and {MAX_THETA_COUNT}, got {theta_count}."
            )
        if symmetric and theta_count % 2 != 0:
            raise ValueError("theta count must be even when the model is treated as symmetric.")


def theta_angles(theta_count: int, *, symmetric: bool = False) -> list[tuple[float, float]]:
    """Return ``(theta_deg, weight)`` pairs for equally spaced roll angles.

    The angles are ``360 * k / theta_count`` reported in (-180, 180]. Equal spacing makes
    the weighted mean the trapezoidal rule for a periodic function, which integrates every
    harmonic below ``theta_count`` exactly. With ``symmetric``, the model is assumed to be
    mirror-symmetric about the XZ plane, so theta and 180 - theta give the same section;
    only one of each pair is calculated, in [-90, 90], with twice the weight.
    """

    if theta_count < 1:
        raise ValueError("theta count must be at least 1.")
    if symmetric and theta_count % 2 != 0:
        raise ValueError("theta count must be even when the model is treated as symmetric.")
    weights: dict[int, int] = {}
    for k in range(theta_count):
        if symmetric:
            mirror = (theta_count // 2 - k) % theta_count
            # Keep whichever of the pair lies in [-90, 90].
            if _in_right_half(mirror, theta_count) and not _in_right_half(k, theta_count):
                k = mirror
        weights[k] = weights.get(k, 0) + 1
    angles = [
        (_wrap_degrees(360.0 * k / theta_count), count / theta_count)
        for k, count in weights.items()
    ]
    return sorted(angles)


def _in_right_half(k: int, count: int) -> bool:
    # True when 360 k / count lies in [-90, 90] (mod 360); compared in integers.
    return 4 * k <= count or 4 * k >= 3 * count


def _wrap_degrees(angle: float) -> float:
    wrapped = math.fmod(angle, 360.0)
    if wrapped > 180.0:
        wrapped -= 360.0
    elif wrapped <= -180.0:
        wrapped += 360.0
    return wrapped + 0.0


def cut_direction(mach: float, theta_deg: float | None) -> FloatArray:
    """Return the (unnormalized) normal ``n`` of the cutting planes ``n . p = x0``."""

    if mach <= 1.0 or theta_deg is None:
        return np.array([1.0, 0.0, 0.0])
    beta = math.sqrt(mach * mach - 1.0)
    theta = math.radians(theta_deg)
    # Exact quarter turns keep the unused axis at exactly zero.
    cos_t, sin_t = _cos_sin_degrees(theta_deg, theta)
    return np.array([1.0, -beta * cos_t, -beta * sin_t])


def _cos_sin_degrees(theta_deg: float, theta: float) -> tuple[float, float]:
    if theta_deg % 90.0 == 0.0:
        quadrant = int((theta_deg % 360.0) / 90.0)
        return ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))[quadrant]
    return math.cos(theta), math.sin(theta)


def prepare_section_mesh(model: ModelData) -> SectionMesh:
    vertices = np.asarray(model.vertices, dtype=float)
    faces = np.asarray(model.faces, dtype=np.int64)
    if faces.size == 0:
        empty = np.zeros((0, 3), dtype=np.int64)
        return SectionMesh(
            vertices=np.zeros((0, 3)),
            faces=empty,
            edges=np.zeros((0, 2), dtype=np.int64),
            face_edges=empty,
            closed_oriented=False,
            orientation=1.0,
        )
    welded_vertices, welded = np.unique(vertices, axis=0, return_inverse=True)
    welded = welded.reshape(-1).astype(np.int64)
    faces = welded[faces]
    keep = (
        (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 2] != faces[:, 0])
    )
    faces = faces[keep]
    starts = faces.reshape(-1)
    ends = faces[:, [1, 2, 0]].reshape(-1)
    low = np.minimum(starts, ends)
    high = np.maximum(starts, ends)
    vertex_count = int(welded_vertices.shape[0])
    keys = low * vertex_count + high
    unique_keys, edge_index = np.unique(keys, return_inverse=True)
    edges = np.column_stack((unique_keys // vertex_count, unique_keys % vertex_count))
    face_edges = edge_index.reshape(-1, 3).astype(np.int64)

    # Closed and consistently oriented: every directed edge is matched by its reverse.
    forward = np.sort(starts * vertex_count + ends)
    backward = np.sort(ends * vertex_count + starts)
    closed_oriented = bool(forward.size > 0 and np.array_equal(forward, backward))
    orientation = 1.0
    if closed_oriented:
        corners = welded_vertices[faces]
        signed_volume = float(
            np.einsum("ij,ij->i", corners[:, 0], np.cross(corners[:, 1], corners[:, 2])).sum()
        )
        orientation = -1.0 if signed_volume < 0.0 else 1.0
    return SectionMesh(
        vertices=welded_vertices,
        faces=faces,
        edges=edges.astype(np.int64),
        face_edges=face_edges,
        closed_oriented=closed_oriented,
        orientation=orientation,
    )


@dataclass(frozen=True)
class _StationSegments:
    """Oriented crossing segments of one cutting plane, in YZ coordinates."""

    start: FloatArray
    end: FloatArray
    start_nodes: IntArray
    end_nodes: IntArray


@dataclass(frozen=True)
class SeriesCut:
    """All crossing segments of one series of parallel cutting planes."""

    direction: FloatArray
    stations: FloatArray
    segments: tuple[_StationSegments, ...]


def cut_series(mesh: SectionMesh, direction: FloatArray, section_count: int) -> SeriesCut:
    """Cut the mesh with ``section_count`` equally spaced planes ``direction . p = x0``.

    The planes run from the lowest to the highest value of ``direction . p`` on the mesh.
    A vertex exactly on a plane counts as lying past it, which is the same as moving the
    plane infinitely little toward lower ``x0``. Every crossing therefore cuts exactly two
    edges of a triangle, faces lying in a plane are never cut, the first plane is empty,
    and the last one gives the section just before the end of the body (a flat base
    included).
    """

    if mesh.faces.shape[0] == 0:
        stations = np.zeros(section_count)
        empty = _StationSegments(
            np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0, np.int64), np.zeros(0, np.int64)
        )
        return SeriesCut(direction, stations, tuple(empty for _ in range(section_count)))
    vertex_s = mesh.vertices @ direction
    face_s = vertex_s[mesh.faces]
    stations = np.linspace(float(vertex_s.min()), float(vertex_s.max()), section_count)
    face_min = face_s.min(axis=1)
    face_max = face_s.max(axis=1)
    # A face crosses plane x0 when face_min < x0 <= face_max.
    first = np.searchsorted(stations, face_min, side="right")
    last = np.searchsorted(stations, face_max, side="right") - 1
    counts = np.maximum(last - first + 1, 0)
    total = int(counts.sum())
    face_index = np.repeat(np.arange(mesh.faces.shape[0]), counts)
    offsets = np.repeat(np.cumsum(counts) - counts, counts)
    station_index = first[face_index] + (np.arange(total) - offsets)

    planes = stations[station_index]
    past = face_s[face_index] >= planes[:, None]
    lone_past = past.sum(axis=1) == 1
    lone = np.where(lone_past, np.argmax(past, axis=1), np.argmin(past, axis=1))
    edge_after = mesh.face_edges[face_index, lone]
    edge_before = mesh.face_edges[face_index, (lone + 2) % 3]
    # With counter-clockwise faces around their outward normal, the section boundary runs
    # counter-clockwise around +X in the YZ plane when it goes from the edge after a lone
    # vertex past the plane to the edge before it (and the other way round otherwise).
    start_edge = np.where(lone_past, edge_after, edge_before)
    end_edge = np.where(lone_past, edge_before, edge_after)
    start_points = _crossing_points(mesh, vertex_s, start_edge, planes)
    end_points = _crossing_points(mesh, vertex_s, end_edge, planes)

    order = np.argsort(station_index, kind="stable")
    per_station = np.bincount(station_index, minlength=section_count)
    bounds = np.concatenate(([0], np.cumsum(per_station)))
    start_points = start_points[order]
    end_points = end_points[order]
    start_edge = start_edge[order]
    end_edge = end_edge[order]
    segments = tuple(
        _StationSegments(
            start_points[bounds[i] : bounds[i + 1]],
            end_points[bounds[i] : bounds[i + 1]],
            start_edge[bounds[i] : bounds[i + 1]],
            end_edge[bounds[i] : bounds[i + 1]],
        )
        for i in range(section_count)
    )
    return SeriesCut(direction, stations, segments)


def _crossing_points(
    mesh: SectionMesh, vertex_s: FloatArray, edge: IntArray, planes: FloatArray
) -> FloatArray:
    a = mesh.edges[edge, 0]
    b = mesh.edges[edge, 1]
    t = (planes - vertex_s[a]) / (vertex_s[b] - vertex_s[a])
    va = mesh.vertices[a][:, 1:]
    vb = mesh.vertices[b][:, 1:]
    return va + t[:, None] * (vb - va)


@dataclass(frozen=True)
class SectionRegion:
    area: float
    # Shapely geometry of the section in YZ coordinates; None when empty.
    geometry: Any
    open: bool
    fallback: bool


def section_region(
    mesh: SectionMesh, segments: _StationSegments, *, with_geometry: bool = False
) -> SectionRegion:
    """Return the area enclosed by one plane's crossing segments.

    For a closed, consistently oriented mesh a point is inside the section when its
    winding number is at least 1, so overlapping or duplicated bodies are counted once.
    Otherwise the even-odd rule is used on the closed loops, and loose ends (from holes
    in the mesh) are ignored and reported as an open section.
    """

    import shapely

    count = segments.start.shape[0]
    if count == 0:
        return SectionRegion(0.0, None, False, False)
    nodes = np.concatenate((segments.start_nodes, segments.end_nodes))
    _, node_counts = np.unique(nodes, return_counts=True)
    is_open = not mesh.closed_oriented and bool(np.any(node_counts == 1))

    lines = shapely.linestrings(np.stack((segments.start, segments.end), axis=1))
    try:
        noded = _node_lines(shapely, lines)
    except shapely.errors.GEOSException:
        signed = 0.5 * float(
            np.sum(
                segments.start[:, 0] * segments.end[:, 1]
                - segments.end[:, 0] * segments.start[:, 1]
            )
        )
        return SectionRegion(abs(signed), None, is_open, True)

    polygons, cuts, dangles, _invalid = shapely.polygonize_full(shapely.get_parts(noded))
    faces = shapely.get_parts(polygons)
    if faces.size == 0:
        return SectionRegion(0.0, None, is_open, False)
    points = shapely.get_coordinates(shapely.point_on_surface(faces))
    if mesh.closed_oriented:
        winding = _winding_numbers(points, segments.start, segments.end) * mesh.orientation
        inside = winding >= 1
    else:
        boundary = noded
        loose = shapely.union_all(
            np.concatenate((shapely.get_parts(cuts), shapely.get_parts(dangles)))
        )
        if not loose.is_empty:
            boundary = shapely.difference(noded, loose)
        coords, line_index = shapely.get_coordinates(shapely.get_parts(boundary), return_index=True)
        # Consecutive coordinates of the same line form one boundary segment.
        same_line = line_index[:-1] == line_index[1:]
        crossings = _crossing_counts(points, coords[:-1][same_line], coords[1:][same_line])
        inside = crossings % 2 == 1
    area = float(np.sum(shapely.area(faces[inside])))
    geometry = shapely.union_all(faces[inside]) if with_geometry and np.any(inside) else None
    return SectionRegion(area, geometry, is_open, False)


def _node_lines(shapely: Any, lines: np.ndarray) -> Any:
    try:
        return shapely.union_all(lines)
    except shapely.errors.GEOSException:
        bounds = shapely.total_bounds(lines)
        scale = float(np.max(np.abs(bounds))) or 1.0
        return shapely.union_all(lines, grid_size=scale * _NODING_RETRY_RELATIVE_GRID)


def _winding_numbers(points: FloatArray, start: FloatArray, end: FloatArray) -> IntArray:
    result = np.zeros(points.shape[0], dtype=np.int64)
    for offset in range(0, points.shape[0], _WINDING_CHUNK):
        chunk = points[offset : offset + _WINDING_CHUNK]
        pu = chunk[:, 0:1]
        pv = chunk[:, 1:2]
        au, av = start[None, :, 0], start[None, :, 1]
        bu, bv = end[None, :, 0], end[None, :, 1]
        side = (bu - au) * (pv - av) - (pu - au) * (bv - av)
        upward = (av <= pv) & (bv > pv) & (side > 0.0)
        downward = (bv <= pv) & (av > pv) & (side < 0.0)
        result[offset : offset + chunk.shape[0]] = upward.sum(axis=1) - downward.sum(axis=1)
    return result


def _crossing_counts(points: FloatArray, start: FloatArray, end: FloatArray) -> IntArray:
    result = np.zeros(points.shape[0], dtype=np.int64)
    for offset in range(0, points.shape[0], _WINDING_CHUNK):
        chunk = points[offset : offset + _WINDING_CHUNK]
        pu = chunk[:, 0:1]
        pv = chunk[:, 1:2]
        au, av = start[None, :, 0], start[None, :, 1]
        bu, bv = end[None, :, 0], end[None, :, 1]
        straddles = (av > pv) != (bv > pv)
        with np.errstate(divide="ignore", invalid="ignore"):
            crossing_u = au + (pv - av) * (bu - au) / (bv - av)
        result[offset : offset + chunk.shape[0]] = (straddles & (crossing_u > pu)).sum(axis=1)
    return result


def section_outline(
    model_or_mesh: ModelData | SectionMesh, *, mach: float, theta_deg: float | None, x0: float
) -> list[FloatArray]:
    """Return the outline of one section as closed 3D polylines in model coordinates."""

    import shapely

    mesh = (
        model_or_mesh
        if isinstance(model_or_mesh, SectionMesh)
        else prepare_section_mesh(model_or_mesh)
    )
    direction = cut_direction(mach, theta_deg)
    cut = _cut_single_plane(mesh, direction, x0)
    region = section_region(mesh, cut, with_geometry=True)
    if region.geometry is None:
        return []
    loops: list[FloatArray] = []
    for polygon in shapely.get_parts(region.geometry):
        rings = [polygon.exterior, *polygon.interiors]
        for ring in rings:
            yz = np.asarray(ring.coords, dtype=float)
            x = x0 - direction[1] * yz[:, 0] - direction[2] * yz[:, 1]
            loops.append(np.column_stack((x, yz)))
    return loops


def _cut_single_plane(mesh: SectionMesh, direction: FloatArray, x0: float) -> _StationSegments:
    if mesh.faces.shape[0] == 0:
        return _StationSegments(
            np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0, np.int64), np.zeros(0, np.int64)
        )
    vertex_s = mesh.vertices @ direction
    face_s = vertex_s[mesh.faces]
    crossing = (face_s.min(axis=1) < x0) & (face_s.max(axis=1) >= x0)
    face_index = np.flatnonzero(crossing)
    planes = np.full(face_index.shape[0], float(x0))
    past = face_s[face_index] >= planes[:, None]
    lone_past = past.sum(axis=1) == 1
    lone = np.where(lone_past, np.argmax(past, axis=1), np.argmin(past, axis=1))
    edge_after = mesh.face_edges[face_index, lone]
    edge_before = mesh.face_edges[face_index, (lone + 2) % 3]
    start_edge = np.where(lone_past, edge_after, edge_before)
    end_edge = np.where(lone_past, edge_before, edge_after)
    return _StationSegments(
        _crossing_points(mesh, vertex_s, start_edge, planes),
        _crossing_points(mesh, vertex_s, end_edge, planes),
        start_edge,
        end_edge,
    )


def calculate_sections(
    model: ModelData,
    *,
    section_count: int = DEFAULT_SECTION_COUNT,
    mach: float = 1.0,
    theta_count: int = DEFAULT_THETA_COUNT,
    symmetric: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
    cancel_callback: Callable[[], None] | None = None,
    mesh: SectionMesh | None = None,
) -> CrossSectionResult:
    """Calculate the cross-sectional area distribution of a loaded model."""

    validate_section_options(
        section_count=section_count, mach=mach, theta_count=theta_count, symmetric=symmetric
    )
    start = perf_counter()
    if mesh is None:
        mesh = prepare_section_mesh(model)
    angles: list[tuple[float | None, float]]
    if mach > 1.0:
        angles = list(theta_angles(theta_count, symmetric=symmetric))
    else:
        angles = [(None, 1.0)]
    total = len(angles) * section_count
    done = 0
    series: list[SectionSeries] = []
    open_total = 0
    fallback_total = 0
    for theta_deg, weight in angles:
        if cancel_callback is not None:
            cancel_callback()
        series_start = perf_counter()
        cut = cut_series(mesh, cut_direction(mach, theta_deg), section_count)
        areas = np.zeros(section_count)
        open_flags = np.zeros(section_count, dtype=bool)
        for index, segments in enumerate(cut.segments):
            if cancel_callback is not None:
                cancel_callback()
            region = section_region(mesh, segments)
            areas[index] = region.area
            open_flags[index] = region.open
            fallback_total += int(region.fallback)
            done += 1
            if progress_callback is not None:
                progress_callback(done, total)
        item = SectionSeries(
            theta_deg=theta_deg,
            weight=weight,
            x=cut.stations,
            area=areas,
            open_flags=open_flags,
            elapsed_sec=perf_counter() - series_start,
        )
        open_total += item.open_sections
        series.append(item)

    warnings: list[str] = []
    if any(_blunt_start(item) for item in series):
        warnings.append(
            "The body starts with a blunt face; the wave drag D/q assumes a slender body "
            "with a pointed nose and is not meaningful here."
        )
    if open_total:
        warnings.append(
            f"{open_total} section(s) cross holes in the mesh; their areas include only "
            "closed outlines and may be too small."
        )
    if fallback_total:
        warnings.append(
            f"{fallback_total} section outline(s) could not be built; their areas were summed "
            "without removing overlaps."
        )
    return CrossSectionResult(
        model=model,
        mach=float(mach),
        section_count=section_count,
        theta_count=theta_count if mach > 1.0 else 1,
        symmetric=bool(symmetric and mach > 1.0),
        series=tuple(series),
        warnings=tuple(warnings),
        elapsed_sec=perf_counter() - start,
    )


# A nose whose first section past the tip already has this fraction of the largest area is
# treated as blunt.
_BLUNT_START_FRACTION = 0.25


def _blunt_start(series: SectionSeries) -> bool:
    if series.area.shape[0] < 2:
        return False
    max_area = series.max_area
    return max_area > 0.0 and float(series.area[1]) > _BLUNT_START_FRACTION * max_area


def wave_drag_terms(station_count: int) -> int:
    """Number of sine terms fitted to a section-area distribution.

    Truncating the series is what smooths the area curve: wave drag weights term n by n,
    so tessellation noise in the highest terms would otherwise dominate.
    """

    return max(2, min(30, (station_count - 1) // 4))


def wave_drag_area(x: FloatArray, area: FloatArray, *, terms: int | None = None) -> float | None:
    """Zero-lift wave drag D/q of a slender body with the given area distribution.

    Uses the von Karman slender-body result
    ``D/q = -1/(2 pi) int int S''(x1) S''(x2) ln|x1 - x2| dx1 dx2`` in its Fourier form:
    with ``x = L (1 - cos phi) / 2`` and ``S'(x) = sum A_n sin(n phi)``,
    ``D/q = pi/4 sum n A_n^2``. The coefficients are fitted to S(x) by least squares, so
    the body is taken to start with zero area and zero slope and to end with zero slope
    (a flat base is allowed). The result is in the square of the length unit.
    """

    x = np.asarray(x, dtype=float)
    area = np.asarray(area, dtype=float)
    if x.shape[0] < 4 or x.shape != area.shape:
        return None
    length = float(x[-1] - x[0])
    if not length > 0.0 or not np.all(np.isfinite(area)):
        return None
    count = terms if terms is not None else wave_drag_terms(x.shape[0])
    count = max(1, min(count, x.shape[0] - 1))
    phi = np.arccos(np.clip(1.0 - 2.0 * (x - x[0]) / length, -1.0, 1.0))
    basis = np.empty((x.shape[0], count))
    basis[:, 0] = length / 4.0 * (phi - np.sin(2.0 * phi) / 2.0)
    for n in range(2, count + 1):
        basis[:, n - 1] = (
            length / 4.0 * (np.sin((n - 1) * phi) / (n - 1) - np.sin((n + 1) * phi) / (n + 1))
        )
    coefficients, *_ = np.linalg.lstsq(basis, area, rcond=None)
    orders = np.arange(1, count + 1)
    return float(math.pi / 4.0 * np.sum(orders * coefficients**2))


def sears_haack_area(x: FloatArray, *, volume: float) -> FloatArray:
    """Sears-Haack body area at the stations ``x``, with the same length and volume."""

    x = np.asarray(x, dtype=float)
    length = float(x[-1] - x[0]) if x.size else 0.0
    if not length > 0.0 or not volume > 0.0:
        return np.zeros_like(x)
    xi = np.clip((x - x[0]) / length, 0.0, 1.0)
    max_area = 16.0 * volume / (3.0 * math.pi * length)
    return max_area * (4.0 * xi * (1.0 - xi)) ** 1.5


def sears_haack_drag_area(*, length: float, volume: float) -> float | None:
    """D/q of the minimum-wave-drag body of the given length and volume."""

    if not length > 0.0 or not volume > 0.0:
        return None
    return 128.0 * volume * volume / (math.pi * length**4)


def _weighted_mean(values: list[tuple[float, float | None]]) -> float | None:
    if not values or any(value is None for _, value in values):
        return None
    total = sum(weight for weight, _ in values)
    return sum(weight * value for weight, value in values if value is not None) / total


def _method_name(model: ModelData) -> str:
    if model.source_format == "step":
        assembly = "-assembly" if model.is_assembly else ""
        component_mode = "-subtract" if model.step_component_mode == "subtract" else ""
        return f"step{component_mode}{assembly}+mesh-sections"
    assembly = "-assembly" if model.is_assembly else ""
    return f"stl-mesh{assembly}-sections"
