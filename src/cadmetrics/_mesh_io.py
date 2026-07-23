from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from cadmetrics.coordinates import parse_axis_map
from cadmetrics.types import ModelData
from cadmetrics.units import area_scale, length_scale, normalize_unit, volume_scale


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
    is_watertight = bool(mesh.is_watertight)
    if not is_watertight:
        warnings.append("Mesh is not watertight; volume is unavailable.")

    volume = (
        abs(float(mesh.volume)) * volume_scale(resolved_input_unit, output_unit)
        if is_watertight
        else None
    )
    surface_area = float(mesh.area) * area_scale(resolved_input_unit, output_unit)
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
        is_watertight=is_watertight,
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
    volume, surface_area, is_watertight = _mesh_volume_and_surface_area(vertices, faces)
    if is_watertight is not True or any(model.is_watertight is not True for model in models):
        volume = None
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
        surface_area=surface_area,
        base_area=base_area,
        is_watertight=is_watertight,
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
    try:
        import trimesh
    except ImportError as exc:
        raise RuntimeError("Mesh metric mode requires the 'trimesh' dependency.") from exc

    if vertices.size == 0 or faces.size == 0:
        return None, None, False

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.merge_vertices()
    return abs(float(mesh.volume)), float(mesh.area), bool(mesh.is_watertight)


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
