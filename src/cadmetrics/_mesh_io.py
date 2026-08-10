from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from cadmetrics.coordinates import parse_axis_map
from cadmetrics.types import ModelData
from cadmetrics.units import area_scale, length_scale, normalize_unit, volume_scale


_NOT_WATERTIGHT_WARNING = "Mesh is not watertight; volume is unavailable."
_INCONSISTENT_WINDING_WARNING = (
    "Mesh face winding is inconsistent; volume is unavailable."
)
_OPPOSING_SHELLS_WARNING = (
    "Mesh contains closed shells with opposing face orientations; signed shell volumes "
    "may cancel, so volume is unavailable."
)
_INVALID_SHELL_VOLUME_WARNING = (
    "Mesh has a closed shell with an invalid or near-zero signed volume; "
    "volume is unavailable."
)


@dataclass(frozen=True)
class _MeshMetrics:
    volume: float | None
    surface_area: float | None
    is_watertight: bool
    volume_warning: str | None


@dataclass(frozen=True)
class _MeshShell:
    triangles: np.ndarray
    signed_volume: float


def _load_stl(
    path: Path,
    *,
    input_unit: str,
    output_unit: str,
    base_axis_map: str,
    base_tolerance: float,
) -> ModelData:
    try:
        import trimesh
    except ImportError as exc:
        raise RuntimeError("STL support requires the 'trimesh' dependency.") from exc

    loaded: Any = trimesh.load(path, force="mesh", process=False)
    if isinstance(loaded, trimesh.Scene):
        loaded = loaded.dump(concatenate=True)
    if isinstance(loaded, list):
        loaded = trimesh.util.concatenate(loaded)
    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError(f"Could not load STL mesh from {path}")
    mesh = loaded
    mesh = mesh.copy()
    mesh.merge_vertices()

    resolved_input_unit = "m" if input_unit.strip().lower() == "auto" else input_unit
    scale = length_scale(resolved_input_unit, output_unit)
    warnings: list[str] = []
    metrics = _trimesh_metrics(mesh)
    if metrics.volume_warning is not None:
        warnings.append(metrics.volume_warning)

    volume = (
        metrics.volume * volume_scale(resolved_input_unit, output_unit)
        if metrics.volume is not None
        else None
    )
    surface_area = (
        metrics.surface_area * area_scale(resolved_input_unit, output_unit)
        if metrics.surface_area is not None
        else None
    )
    native_vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    native_diagonal = _mesh_bounding_box_diagonal(native_vertices)
    base_area, base_found = _mesh_xmax_base_area(
        native_vertices,
        faces,
        base_axis_map=base_axis_map,
        scale=scale,
        native_diagonal=native_diagonal,
        relative_tolerance=base_tolerance,
    )
    if not base_found:
        warnings.append("Could not find an Xmax base face; base_area set to 0.")
    return ModelData(
        path=path,
        source_format="stl",
        vertices=native_vertices * scale,
        faces=faces,
        input_unit=normalize_unit(resolved_input_unit),
        output_unit=normalize_unit(output_unit),
        volume=volume,
        surface_area=surface_area,
        base_area=base_area,
        is_watertight=metrics.is_watertight,
        mesh_deflection=None,
        angular_deflection=None,
        base_tolerance=base_tolerance,
        warnings=tuple(warnings),
    )


def _load_stl_assembly(
    paths: tuple[Path, ...],
    *,
    input_unit: str,
    output_unit: str,
    base_axis_map: str,
    base_tolerance: float,
) -> ModelData:
    models = [
        _load_stl(
            path,
            input_unit=input_unit,
            output_unit=output_unit,
            base_axis_map=base_axis_map,
            base_tolerance=base_tolerance,
        )
        for path in paths
    ]
    vertices, faces = _combine_meshes(
        [(model.vertices, model.faces) for model in models]
    )
    metrics = _mesh_metrics(vertices, faces)
    valid_component_volumes = [model.volume for model in models]
    volume = (
        math.fsum(value for value in valid_component_volumes if value is not None)
        if metrics.is_watertight
        and all(value is not None for value in valid_component_volumes)
        else None
    )
    base_area, base_found = _mesh_xmax_base_area(
        vertices,
        faces,
        base_axis_map=base_axis_map,
        scale=1.0,
        native_diagonal=_mesh_bounding_box_diagonal(vertices),
        relative_tolerance=base_tolerance,
    )
    warnings = [
        "STL assembly meshes were concatenated without boolean union; overlapping volume and surface area may double-count."
    ]
    if metrics.volume_warning is not None and not metrics.is_watertight:
        warnings.append(metrics.volume_warning)
    if not base_found:
        warnings.append("Could not find an Xmax base face; base_area set to 0.")
    for model in models:
        warnings.extend(model.warnings)

    return ModelData(
        path=_assembly_path(paths),
        source_format="stl",
        vertices=vertices,
        faces=faces,
        input_unit=models[0].input_unit,
        output_unit=normalize_unit(output_unit),
        volume=volume,
        surface_area=metrics.surface_area,
        base_area=base_area,
        is_watertight=metrics.is_watertight,
        mesh_deflection=None,
        angular_deflection=None,
        base_tolerance=base_tolerance,
        is_assembly=True,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _mesh_volume_and_surface_area(
    vertices: np.ndarray,
    faces: np.ndarray,
) -> tuple[float | None, float | None, bool]:
    metrics = _mesh_metrics(vertices, faces)
    return metrics.volume, metrics.surface_area, metrics.is_watertight


def _mesh_metrics(vertices: np.ndarray, faces: np.ndarray) -> _MeshMetrics:
    try:
        import trimesh
    except ImportError as exc:
        raise RuntimeError("Mesh metric mode requires the 'trimesh' dependency.") from exc

    if vertices.size == 0 or faces.size == 0:
        return _MeshMetrics(None, None, False, _NOT_WATERTIGHT_WARNING)

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.merge_vertices()
    return _trimesh_metrics(mesh)


def _trimesh_metrics(mesh: Any) -> _MeshMetrics:
    surface_area = float(mesh.area)
    is_watertight = bool(mesh.is_watertight)
    if not is_watertight:
        return _MeshMetrics(None, surface_area, False, _NOT_WATERTIGHT_WARNING)
    if not bool(mesh.is_winding_consistent):
        return _MeshMetrics(None, surface_area, True, _INCONSISTENT_WINDING_WARNING)

    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    face_adjacency = np.asarray(mesh.face_adjacency, dtype=np.int64)
    shells = _mesh_shells(vertices, faces, face_adjacency)
    if not shells or any(not _valid_signed_volume(shell.signed_volume) for shell in shells):
        return _MeshMetrics(None, surface_area, True, _INVALID_SHELL_VOLUME_WARNING)

    has_positive_shell = any(shell.signed_volume > 0.0 for shell in shells)
    has_negative_shell = any(shell.signed_volume < 0.0 for shell in shells)
    if has_positive_shell and has_negative_shell:
        volume = _nested_shell_volume(shells)
        if volume is None:
            return _MeshMetrics(None, surface_area, True, _OPPOSING_SHELLS_WARNING)
        return _MeshMetrics(volume, surface_area, True, None)

    volume = math.fsum(abs(shell.signed_volume) for shell in shells)
    if not math.isfinite(volume):
        return _MeshMetrics(None, surface_area, True, _INVALID_SHELL_VOLUME_WARNING)
    return _MeshMetrics(volume, surface_area, True, None)


def _mesh_shells(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_adjacency: np.ndarray,
) -> tuple[_MeshShell, ...]:
    parents = list(range(int(faces.shape[0])))

    def find(face_index: int) -> int:
        while parents[face_index] != face_index:
            parents[face_index] = parents[parents[face_index]]
            face_index = parents[face_index]
        return face_index

    for left, right in face_adjacency:
        left_root = find(int(left))
        right_root = find(int(right))
        if left_root != right_root:
            parents[right_root] = left_root

    shell_faces: dict[int, list[int]] = {}
    for face_index in range(int(faces.shape[0])):
        shell_faces.setdefault(find(face_index), []).append(face_index)

    shells: list[_MeshShell] = []
    for indices in shell_faces.values():
        triangles = vertices[faces[np.asarray(indices, dtype=np.int64)]]
        reference = triangles[0, 0]
        relative = triangles - reference
        six_volumes = np.einsum(
            "ij,ij->i",
            relative[:, 0],
            np.cross(relative[:, 1], relative[:, 2]),
        )
        signed_six_volume = math.fsum(float(value) for value in six_volumes)
        absolute_six_volume = math.fsum(abs(float(value)) for value in six_volumes)
        roundoff_tolerance = (
            np.finfo(float).eps * max(absolute_six_volume, np.finfo(float).tiny) * 16.0
        )
        if abs(signed_six_volume) <= roundoff_tolerance:
            signed_six_volume = 0.0
        shells.append(
            _MeshShell(
                triangles=triangles,
                signed_volume=signed_six_volume / 6.0,
            )
        )
    return tuple(shells)


def _nested_shell_volume(shells: tuple[_MeshShell, ...]) -> float | None:
    contains = [[False] * len(shells) for _ in shells]
    for parent_index, parent in enumerate(shells):
        for child_index, child in enumerate(shells):
            if parent_index == child_index or not _bounds_strictly_contain(parent, child):
                continue
            contained = _shell_contains(parent, child)
            if contained is None:
                return None
            contains[parent_index][child_index] = contained

    containers = [
        tuple(parent for parent in range(len(shells)) if contains[parent][child])
        for child in range(len(shells))
    ]
    for shell_containers in containers:
        for index, first in enumerate(shell_containers):
            for second in shell_containers[index + 1 :]:
                if not (contains[first][second] or contains[second][first]):
                    return None

    depths = tuple(len(shell_containers) for shell_containers in containers)
    normalized_signs = {
        (1 if shell.signed_volume > 0.0 else -1) * (-1 if depth % 2 else 1)
        for shell, depth in zip(shells, depths, strict=True)
    }
    if len(normalized_signs) != 1:
        return None

    volume_terms = [
        abs(shell.signed_volume) * (-1 if depth % 2 else 1)
        for shell, depth in zip(shells, depths, strict=True)
    ]
    volume = math.fsum(volume_terms)
    absolute_volume = math.fsum(abs(value) for value in volume_terms)
    tolerance = np.finfo(float).eps * max(absolute_volume, np.finfo(float).tiny) * 16.0
    if not math.isfinite(volume) or volume <= tolerance:
        return None
    return volume


def _bounds_strictly_contain(parent: _MeshShell, child: _MeshShell) -> bool:
    parent_points = parent.triangles.reshape(-1, 3)
    child_points = child.triangles.reshape(-1, 3)
    parent_min = np.min(parent_points, axis=0)
    parent_max = np.max(parent_points, axis=0)
    child_min = np.min(child_points, axis=0)
    child_max = np.max(child_points, axis=0)
    coordinate_scale = max(
        1.0,
        float(np.max(np.abs(parent_points))),
        float(np.max(parent_max - parent_min)),
    )
    tolerance = np.finfo(float).eps * coordinate_scale * 64.0
    return bool(
        np.all(child_min > parent_min + tolerance)
        and np.all(child_max < parent_max - tolerance)
    )


def _shell_contains(parent: _MeshShell, child: _MeshShell) -> bool | None:
    child_points = child.triangles.reshape(-1, 3)
    point_indices = {0}
    for axis in range(3):
        point_indices.add(int(np.argmin(child_points[:, axis])))
        point_indices.add(int(np.argmax(child_points[:, axis])))

    classifications = {
        _point_inside_shell(child_points[index], parent.triangles)
        for index in point_indices
    }
    if None in classifications or len(classifications) != 1:
        return None
    return classifications.pop()


def _point_inside_shell(point: np.ndarray, triangles: np.ndarray) -> bool | None:
    vectors = triangles - point
    lengths = np.linalg.norm(vectors, axis=2)
    if bool(np.any(lengths == 0.0)):
        return None
    unit_vectors = vectors / lengths[:, :, np.newaxis]
    first = unit_vectors[:, 0]
    second = unit_vectors[:, 1]
    third = unit_vectors[:, 2]
    numerators = np.einsum("ij,ij->i", first, np.cross(second, third))
    denominators = (
        1.0
        + np.einsum("ij,ij->i", first, second)
        + np.einsum("ij,ij->i", second, third)
        + np.einsum("ij,ij->i", third, first)
    )
    solid_angle = math.fsum(
        float(value)
        for value in 2.0 * np.arctan2(numerators, denominators)
    )
    winding = abs(solid_angle) / (4.0 * math.pi)
    if math.isclose(winding, 1.0, rel_tol=1.0e-7, abs_tol=1.0e-7):
        return True
    if winding <= 1.0e-7:
        return False
    return None


def _valid_signed_volume(value: float) -> bool:
    return math.isfinite(value) and value != 0.0


def _mesh_xmax_base_area(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    base_axis_map: str,
    scale: float,
    native_diagonal: float,
    relative_tolerance: float,
    excluded_face_indices: Sequence[int] = (),
) -> tuple[float, bool]:
    if vertices.size == 0 or faces.size == 0:
        return 0.0, False

    source_axis, sign = _base_source_axis(base_axis_map)
    coordinates = vertices[:, source_axis]
    target = float(np.max(coordinates) if sign > 0.0 else np.min(coordinates))
    tolerance = _native_xmax_tolerance(
        native_diagonal=native_diagonal,
        scale=scale,
        relative_tolerance=relative_tolerance,
    )
    face_coordinates = coordinates[faces]
    on_base = np.all(np.abs(face_coordinates - target) <= tolerance, axis=1)
    for face_index in excluded_face_indices:
        if 0 <= face_index < on_base.shape[0]:
            on_base[face_index] = False
    if not bool(np.any(on_base)):
        return 0.0, False

    triangles = vertices[faces[on_base]]
    native_area = float(
        np.sum(
            0.5
            * np.linalg.norm(
                np.cross(
                    triangles[:, 1] - triangles[:, 0],
                    triangles[:, 2] - triangles[:, 0],
                ),
                axis=1,
            )
        )
    )
    return native_area * scale * scale, native_area > 0.0


def _mesh_bounding_box_diagonal(vertices: np.ndarray) -> float:
    if vertices.size == 0:
        return 0.0
    extents = np.max(vertices, axis=0) - np.min(vertices, axis=0)
    return float(np.linalg.norm(extents))


def _combine_meshes(meshes: Sequence[tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    offset = 0
    for mesh_vertices, mesh_faces in meshes:
        vertices.append(mesh_vertices)
        faces.append(mesh_faces + offset)
        offset += int(mesh_vertices.shape[0])
    if not vertices:
        return np.empty((0, 3), dtype=float), np.empty((0, 3), dtype=np.int64)
    return np.vstack(vertices), np.vstack(faces).astype(np.int64, copy=False)


def _empty_mesh() -> tuple[np.ndarray, np.ndarray]:
    return np.empty((0, 3), dtype=float), np.empty((0, 3), dtype=np.int64)


def _assembly_path(paths: Sequence[Path]) -> Path:
    return Path("; ".join(str(path) for path in paths))


def _base_source_axis(base_axis_map: str) -> tuple[int, float]:
    return parse_axis_map(base_axis_map)[0]


def _native_xmax_tolerance(
    *,
    native_diagonal: float,
    scale: float,
    relative_tolerance: float,
) -> float:
    if scale <= 0.0:
        return max(native_diagonal * relative_tolerance, 1.0e-12)
    output_tolerance = max(native_diagonal * scale * relative_tolerance, 1.0e-12)
    return output_tolerance / scale


def _triangle_mesh_surface_area(vertices: np.ndarray, faces: np.ndarray) -> float:
    if vertices.size == 0 or faces.size == 0:
        return 0.0
    triangles = vertices[faces]
    return float(
        np.sum(
            0.5
            * np.linalg.norm(
                np.cross(
                    triangles[:, 1] - triangles[:, 0],
                    triangles[:, 2] - triangles[:, 0],
                ),
                axis=1,
            )
        )
    )
