from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from cadmetrics.api import inspect_model
from cadmetrics.projection import (
    _is_closed_oriented_surface,
    projected_metrics,
    projection_basis,
)
from cadmetrics.types import ModelData

shapely = pytest.importorskip("shapely")
trimesh = pytest.importorskip("trimesh")

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
DIRECTIONS = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
    (-1.0, 0.0, 0.0),
    (1.0, 1.0, 1.0),
    (0.3, -0.7, 0.2),
)
STL_SAMPLES = (
    "box_1x2x3/box_1x2x3_binary.stl",
    "cylinder_x_r1_l2/cylinder_x_r1_l2_binary.stl",
    "sphere_r1/sphere_r1_binary.stl",
    "frame_with_hole/frame_with_hole_binary.stl",
    "two_boxes_intersecting/two_boxes_intersecting_binary.stl",
    "two_boxes_overlap_projection/two_boxes_overlap_projection_binary.stl",
)
STEP_SAMPLES = (
    "box_1x2x3/box_1x2x3.step",
    "cylinder_x_r1_l2/cylinder_x_r1_l2.step",
    "frame_with_hole/frame_with_hole.step",
    "two_boxes_overlap_projection/two_boxes_overlap_projection.step",
)


def _all_triangle_union(model: ModelData, direction: np.ndarray):
    """Reference outline: union of every non-degenerate projected triangle."""

    basis_u, basis_v = projection_basis(direction)
    projected = np.column_stack((model.vertices @ basis_u, model.vertices @ basis_v))
    polygons = shapely.polygons(projected[np.asarray(model.faces)])
    polygons = polygons[shapely.area(polygons) > 0.0]
    return shapely.union_all(polygons)


def _assert_matches_full_union(model: ModelData, direction: np.ndarray) -> None:
    reference = _all_triangle_union(model, direction)
    metrics = projected_metrics(model, direction=direction)
    assert metrics.area == pytest.approx(reference.area, rel=1.0e-12, abs=0.0)
    assert metrics.centroid_u == pytest.approx(reference.centroid.x, rel=1.0e-9, abs=1.0e-12)
    assert metrics.centroid_v == pytest.approx(reference.centroid.y, rel=1.0e-9, abs=1.0e-12)


def _mesh_model(mesh, *, is_watertight: bool | None) -> ModelData:
    model = inspect_model(SAMPLES / "unit_cube/unit_cube_binary.stl")
    return dataclasses.replace(
        model,
        vertices=np.asarray(mesh.vertices, dtype=float),
        faces=np.asarray(mesh.faces, dtype=np.int64),
        is_watertight=is_watertight,
    )


@pytest.mark.parametrize("relative", STL_SAMPLES)
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_closed_stl_samples_use_one_side_and_match_full_union(
    relative: str, direction: tuple[float, float, float]
) -> None:
    model = inspect_model(SAMPLES / relative)
    assert model.is_watertight is True
    assert _is_closed_oriented_surface(model.vertices, np.asarray(model.faces))
    _assert_matches_full_union(model, np.asarray(direction, dtype=float))


@pytest.mark.parametrize("relative", STEP_SAMPLES)
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_closed_step_samples_match_full_union(
    relative: str, direction: tuple[float, float, float]
) -> None:
    pytest.importorskip("OCP")
    model = inspect_model(SAMPLES / relative)
    assert model.is_watertight is True
    assert _is_closed_oriented_surface(model.vertices, np.asarray(model.faces))
    _assert_matches_full_union(model, np.asarray(direction, dtype=float))


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_inward_facing_mesh_matches_full_union(direction: tuple[float, float, float]) -> None:
    mesh = trimesh.creation.cylinder(radius=1.0, height=2.0, sections=24)
    inward = trimesh.Trimesh(mesh.vertices, mesh.faces[:, ::-1], process=False)
    model = _mesh_model(inward, is_watertight=True)
    assert _is_closed_oriented_surface(model.vertices, model.faces)
    _assert_matches_full_union(model, np.asarray(direction, dtype=float))


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_opposing_closed_shells_match_full_union(direction: tuple[float, float, float]) -> None:
    outward = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    inward = trimesh.creation.icosphere(subdivisions=2, radius=0.6)
    inward.apply_translation((0.4, 0.3, 0.2))
    inward = trimesh.Trimesh(inward.vertices, inward.faces[:, ::-1], process=False)
    combined = trimesh.util.concatenate([outward, inward])
    model = _mesh_model(combined, is_watertight=True)
    assert _is_closed_oriented_surface(model.vertices, model.faces)
    _assert_matches_full_union(model, np.asarray(direction, dtype=float))


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_flipped_face_falls_back_to_all_triangles(direction: tuple[float, float, float]) -> None:
    mesh = trimesh.creation.box(extents=(1.0, 2.0, 3.0))
    faces = np.asarray(mesh.faces).copy()
    faces[0] = faces[0, ::-1]
    model = _mesh_model(trimesh.Trimesh(mesh.vertices, faces, process=False), is_watertight=True)
    assert not _is_closed_oriented_surface(model.vertices, model.faces)
    _assert_matches_full_union(model, np.asarray(direction, dtype=float))


def test_duplicated_shared_vertices_are_welded_by_coordinates() -> None:
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    vertices = np.asarray(mesh.vertices)[np.asarray(mesh.faces).reshape(-1)]
    faces = np.arange(len(vertices), dtype=np.int64).reshape(-1, 3)
    assert _is_closed_oriented_surface(vertices, faces)


@pytest.mark.parametrize("is_watertight", [False, None])
def test_unknown_or_open_watertightness_uses_all_triangles(is_watertight: bool | None) -> None:
    # With a face missing, one winding side alone can leave a hole in the outline.
    model = inspect_model(SAMPLES / "open_cube_missing_face/open_cube_missing_face_binary.stl")
    model = dataclasses.replace(model, is_watertight=is_watertight)
    assert not _is_closed_oriented_surface(model.vertices, np.asarray(model.faces))
    for direction in DIRECTIONS:
        _assert_matches_full_union(model, np.asarray(direction, dtype=float))
