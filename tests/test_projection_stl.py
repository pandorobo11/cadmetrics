from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("shapely")

from cadmetrics.api import inspect_model, measure, project, sweep, sweep_model
from cadmetrics._mesh_io import _mesh_xmax_base_area


trimesh = pytest.importorskip("trimesh")
DATA_DIR = Path(__file__).parent / "data"


def _box_mesh(*, reverse: bool = False, flipped_face: int | None = None):
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    faces = np.asarray(mesh.faces, dtype=np.int64).copy()
    if reverse:
        faces = faces[:, ::-1]
    if flipped_face is not None:
        faces[flipped_face] = faces[flipped_face, ::-1]
    return trimesh.Trimesh(vertices=mesh.vertices.copy(), faces=faces, process=False)


def test_cube_projected_area_default_direction() -> None:
    row = project(DATA_DIR / "unit_cube.stl")
    assert row.projected_area == pytest.approx(1.0)
    assert row.direction_x == pytest.approx(1.0)
    assert row.direction_y == pytest.approx(0.0)
    assert row.direction_z == pytest.approx(0.0)
    assert row.centroid_u == pytest.approx(0.5)
    assert row.centroid_v == pytest.approx(0.5)
    assert row.centroid_x == pytest.approx(0.5)
    assert row.centroid_y == pytest.approx(0.5)
    assert row.centroid_z == pytest.approx(0.5)
    assert row.x_min == pytest.approx(0.0)
    assert row.x_max == pytest.approx(1.0)
    assert row.y_min == pytest.approx(0.0)
    assert row.y_max == pytest.approx(1.0)
    assert row.z_min == pytest.approx(0.0)
    assert row.z_max == pytest.approx(1.0)
    assert row.method == "stl-mesh-projection"
    assert row.load_elapsed_sec is not None
    assert row.elapsed_sec is not None


def test_stl_assembly_projects_combined_silhouette_once() -> None:
    path = DATA_DIR / "unit_cube.stl"
    row = project([path, path])

    assert row.projected_area == pytest.approx(1.0)
    assert row.volume is None
    assert row.surface_area == pytest.approx(12.0)
    assert row.base_area == pytest.approx(2.0)
    assert row.method == "stl-mesh-assembly-projection"
    assert row.is_watertight is False
    assert "without boolean union" in "; ".join(row.warnings)


@pytest.mark.parametrize("radius_mm", [0.001, 0.0001])
def test_small_sphere_projection_scales_with_output_unit(
    tmp_path: Path,
    radius_mm: float,
) -> None:
    path = tmp_path / "small_sphere.stl"
    trimesh.creation.icosphere(subdivisions=3, radius=radius_mm).export(path)

    metres = project(path, input_unit="mm", output_unit="m")
    millimetres = project(path, input_unit="mm", output_unit="mm")

    assert millimetres.projected_area is not None
    assert millimetres.projected_area > 0.0
    assert metres.projected_area == pytest.approx(
        millimetres.projected_area * 1.0e-6, rel=1.0e-12, abs=0.0
    )


@pytest.mark.parametrize("side_mm", [4.0e-5, 4.0e-7])
def test_small_triangle_projection_keeps_positive_area_and_centroid(
    tmp_path: Path, side_mm: float
) -> None:
    path = tmp_path / "small_triangle.stl"
    mesh = trimesh.Trimesh(
        vertices=[[0.0, 0.0, 0.0], [0.0, side_mm, 0.0], [0.0, 0.0, side_mm]],
        faces=[[0, 1, 2]],
        process=False,
    )
    mesh.export(path)

    row = project(path, input_unit="mm", output_unit="m")

    side_m = side_mm * 1.0e-3
    # Binary STL stores float32 coordinates; retain that format's precision.
    assert row.projected_area == pytest.approx(0.5 * side_m**2, rel=1.0e-7, abs=0.0)
    assert row.centroid_u == pytest.approx(side_m / 3.0, rel=1.0e-7, abs=0.0)
    assert row.centroid_v == pytest.approx(side_m / 3.0, rel=1.0e-7, abs=0.0)


@pytest.mark.parametrize(
    ("angles", "direction", "normal_axis"),
    [
        ({"alpha_deg": 90}, "0,0,1", 0),
        ({"alpha_deg": -90}, "0,0,-1", 0),
        ({"alpha_deg": 270}, "0,0,-1", 0),
        ({"alpha_deg": 180}, "-1,0,0", 2),
        ({"alpha_deg": 360}, "1,0,0", 2),
        ({"beta_deg": 90}, "0,-1,0", 0),
        ({"beta_deg": -90}, "0,1,0", 0),
        ({"attitude": "roll-pitch", "roll_deg": 90, "pitch_deg": 90}, "0,-1,0", 0),
        ({"attitude": "roll-pitch", "roll_deg": 180, "pitch_deg": 90}, "0,0,-1", 0),
        ({"attitude": "roll-pitch", "roll_deg": 270, "pitch_deg": 90}, "0,1,0", 0),
    ],
)
def test_edge_on_triangle_projection_has_zero_area_and_no_centroid(
    tmp_path: Path, angles, direction: str, normal_axis: int
) -> None:
    path = tmp_path / "edge_on_triangle.stl"
    in_plane_axes = [axis for axis in range(3) if axis != normal_axis]
    mesh = trimesh.Trimesh(
        vertices=[np.zeros(3), *np.eye(3)[in_plane_axes]],
        faces=[[0, 1, 2]],
        process=False,
    )
    mesh.export(path)

    angled = project(path, **angles)
    vector = project(path, attitude="vector", direction=direction)

    for row in (angled, vector):
        assert row.projected_area == 0.0
        assert row.centroid_u is None
        assert row.centroid_v is None
        assert row.centroid_x is None
        assert row.centroid_y is None
        assert row.centroid_z is None
    assert (angled.direction_x, angled.direction_y, angled.direction_z) == (
        vector.direction_x,
        vector.direction_y,
        vector.direction_z,
    )


@pytest.mark.parametrize("alpha", [30.0, np.nextafter(90.0, 0.0), np.nextafter(90.0, 180.0)])
def test_positive_projection_near_edge_on_is_not_snapped_to_zero(
    tmp_path: Path, alpha: float
) -> None:
    path = tmp_path / "triangle.stl"
    trimesh.Trimesh(
        vertices=[[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        faces=[[0, 1, 2]],
        process=False,
    ).export(path)

    row = project(path, alpha_deg=alpha)

    cosine = np.cos(np.deg2rad(alpha))
    assert row.projected_area == pytest.approx(abs(cosine) / 2.0, rel=1.0e-12, abs=0.0)
    # The helper axis changes near Z; both cases have analytical 2D centroids.
    if alpha == 30.0:
        expected_centroid = (1.0 / 3.0, cosine / 3.0)
    else:
        expected_centroid = (-cosine / 3.0, 1.0 / 3.0)
    assert (row.centroid_u, row.centroid_v) == pytest.approx(
        expected_centroid, rel=1.0e-12, abs=0.0
    )


def test_tiny_positive_vector_component_keeps_projected_area(tmp_path: Path) -> None:
    path = tmp_path / "triangle.stl"
    trimesh.Trimesh(
        vertices=[[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        faces=[[0, 1, 2]],
        process=False,
    ).export(path)

    row = project(path, attitude="vector", direction="1e-16,0,1")

    assert row.projected_area == pytest.approx(5.0e-17, rel=1.0e-12, abs=0.0)
    assert row.centroid_u == pytest.approx(-1.0e-16 / 3.0, rel=1.0e-12, abs=0.0)
    assert row.centroid_v == pytest.approx(1.0 / 3.0)


def test_watertight_stl_with_one_reversed_face_leaves_volume_unset(
    tmp_path: Path,
) -> None:
    path = tmp_path / "inconsistent_winding.stl"
    _box_mesh(flipped_face=0).export(path)

    row = measure(path)

    assert row.volume is None
    assert row.surface_area == pytest.approx(6.0)
    assert row.is_watertight is True
    assert "face winding is inconsistent" in "; ".join(row.warnings)


def test_consistently_reversed_stl_uses_absolute_shell_volume(tmp_path: Path) -> None:
    path = tmp_path / "reversed.stl"
    _box_mesh(reverse=True).export(path)

    row = measure(path)

    assert row.volume == pytest.approx(1.0)
    assert row.surface_area == pytest.approx(6.0)
    assert row.is_watertight is True
    assert "winding" not in "; ".join(row.warnings)


@pytest.mark.parametrize("reverse_all", [False, True])
def test_stl_with_nested_cavity_uses_shell_nesting(
    tmp_path: Path,
    reverse_all: bool,
) -> None:
    outer = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    inner = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    inner.faces = inner.faces[:, ::-1]
    combined = trimesh.util.concatenate((outer, inner))
    if reverse_all:
        combined.faces = combined.faces[:, ::-1]
    path = tmp_path / f"nested_cavity_{reverse_all}.stl"
    combined.export(path)

    row = measure(path)

    assert row.volume == pytest.approx(7.0)
    assert row.surface_area == pytest.approx(30.0)
    assert row.is_watertight is True


def test_stl_with_opposing_closed_shells_leaves_volume_unset(tmp_path: Path) -> None:
    outward = _box_mesh()
    inward = _box_mesh(reverse=True)
    inward.apply_translation((2.0, 0.0, 0.0))
    combined = trimesh.util.concatenate((outward, inward))
    path = tmp_path / "opposing_shells.stl"
    combined.export(path)

    row = measure(path)

    assert row.volume is None
    assert row.surface_area == pytest.approx(12.0)
    assert row.is_watertight is True
    assert "opposing face orientations" in "; ".join(row.warnings)


def test_stl_assembly_accepts_individually_valid_reversed_shell(tmp_path: Path) -> None:
    outward_path = tmp_path / "outward.stl"
    inward_path = tmp_path / "inward.stl"
    _box_mesh().export(outward_path)
    inward = _box_mesh(reverse=True)
    inward.apply_translation((2.0, 0.0, 0.0))
    inward.export(inward_path)

    row = measure([outward_path, inward_path])

    assert row.volume == pytest.approx(2.0)
    assert row.surface_area == pytest.approx(12.0)
    assert row.is_watertight is True
    assert "opposing face orientations" not in "; ".join(row.warnings)


def test_sweep_model_checks_cancellation_before_and_after_each_case() -> None:
    model = inspect_model(DATA_DIR / "unit_cube.stl")
    checks = 0
    completed_rows = []

    def cancel_after_first_projection() -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        sweep_model(
            model,
            alpha_deg="0:1:1",
            cancel_callback=cancel_after_first_projection,
            progress_callback=lambda _index, _total, row: completed_rows.append(row),
        )

    assert completed_rows == []


def test_axis_map_rejects_duplicate_source_axes() -> None:
    with pytest.raises(ValueError, match="each source axis exactly once"):
        project(DATA_DIR / "unit_cube.stl", axis_map="x,x,z")


def test_cube_sweep_combinations() -> None:
    rows = sweep(
        DATA_DIR / "unit_cube.stl",
        alpha_deg="0:1:1",
        beta_deg="0:1:1",
    )
    assert len(rows) == 4
    assert all(row.projected_area is not None for row in rows)
    assert all(row.load_elapsed_sec is not None for row in rows)
    assert all(row.elapsed_sec is not None for row in rows)


@pytest.mark.parametrize("direction", ["nan,0,0", "1,-inf,0"])
def test_vector_direction_rejects_non_finite_components(direction: str) -> None:
    with pytest.raises(ValueError, match="finite"):
        project(DATA_DIR / "unit_cube.stl", attitude="vector", direction=direction)


def test_roll_pitch_api_uses_explicit_degree_arguments() -> None:
    row = project(
        DATA_DIR / "unit_cube.stl",
        attitude="roll-pitch",
        roll_deg=30,
        pitch_deg=60,
    )

    assert row.direction_x == pytest.approx(0.5)
    assert row.direction_y == pytest.approx(-0.4330127018922193)
    assert row.direction_z == pytest.approx(0.75)
    assert row.roll_deg == pytest.approx(30.0)
    assert row.pitch_deg == pytest.approx(60.0)


def test_roll_pitch_sweep_reports_public_angles_to_progress_callback() -> None:
    progress = []

    rows = sweep(
        DATA_DIR / "unit_cube.stl",
        attitude="roll-pitch",
        roll_deg="0:90:90",
        pitch_deg=90,
        progress_callback=lambda index, total, row: progress.append(
            (index, total, row.roll_deg, row.pitch_deg)
        ),
    )

    assert len(rows) == 2
    assert progress == [(1, 2, 0.0, 90.0), (2, 2, 90.0, 90.0)]


def test_vector_sweep_returns_one_row() -> None:
    rows = sweep(
        DATA_DIR / "unit_cube.stl",
        attitude="vector",
        direction="0,1,0",
    )

    assert len(rows) == 1
    assert rows[0].direction_y == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("action", "kwargs", "argument"),
    [
        (project, {"attitude": "roll-pitch", "alpha_deg": 10}, "alpha_deg"),
        (project, {"attitude": "alpha-beta", "pitch_deg": 10}, "pitch_deg"),
        (
            project,
            {"attitude": "vector", "direction": "1,0,0", "roll_deg": 10},
            "roll_deg",
        ),
        (project, {"attitude": "vector"}, "direction is required"),
        (project, {"attitude": "yaw-pitch"}, "attitude must be one of"),
        (project, {"alpha_deg": float("nan")}, "alpha_deg must be finite"),
        (
            project,
            {"attitude": "roll-pitch", "pitch_deg": float("inf")},
            "pitch_deg must be finite",
        ),
        (sweep, {"attitude": "vector", "direction": None}, "direction is required"),
        (sweep, {"attitude": "vector", "direction": "0,0,0"}, "greater than zero"),
        (sweep, {"alpha_deg": "bad"}, "could not convert"),
        (
            sweep,
            {"alpha_deg": "0:100:1", "beta_deg": "0:100:1"},
            "maximum is 10,000",
        ),
    ],
)
def test_public_api_validates_attitude_before_loading(
    monkeypatch: pytest.MonkeyPatch,
    action,
    kwargs: dict[str, object],
    argument: str,
) -> None:
    def unexpected_load(*_args, **_kwargs):
        raise AssertionError("model loading must not run for an invalid attitude")

    monkeypatch.setattr("cadmetrics.api._inspect_model_with_options", unexpected_load)

    with pytest.raises(ValueError, match=argument):
        action(Path("not-loaded.step"), **kwargs)


def test_mixed_step_and_stl_assembly_is_rejected_before_loading() -> None:
    with pytest.raises(ValueError, match="mixed STEP and STL"):
        measure([Path("not-loaded.step"), Path("not-loaded.stl")])


def test_base_area_default_tolerance_allows_small_xmax_face_variation() -> None:
    vertices = np.array(
        [
            [1.0, 0.0, 0.0],
            [1.0 - 5.0e-7, 1.0, 0.0],
            [1.0, 1.0, 1.0],
            [1.0 - 5.0e-7, 0.0, 1.0],
        ],
        dtype=float,
    )
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)

    default_area, default_found = _mesh_xmax_base_area(
        vertices,
        faces,
        base_axis_map="x,y,z",
        scale=1.0,
        native_diagonal=1.0,
        relative_tolerance=1.0e-6,
    )
    strict_area, strict_found = _mesh_xmax_base_area(
        vertices,
        faces,
        base_axis_map="x,y,z",
        scale=1.0,
        native_diagonal=1.0,
        relative_tolerance=1.0e-8,
    )

    assert default_found is True
    assert default_area == pytest.approx(1.0)
    assert strict_found is False
    assert strict_area == pytest.approx(0.0)
