from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("shapely")
pytest.importorskip("trimesh")

from cadmetrics.api import inspect_model, measure, project, sweep, sweep_model
from cadmetrics._mesh_io import _mesh_xmax_base_area


DATA_DIR = Path(__file__).parent / "data"


def test_cube_measurements() -> None:
    row = measure(DATA_DIR / "unit_cube.stl")
    assert row.volume == pytest.approx(1.0)
    assert row.surface_area == pytest.approx(6.0)
    assert row.base_area == pytest.approx(1.0)
    assert row.is_watertight is True
    assert row.cadmetrics_version
    assert row.cadmetrics_hash


def test_stl_assembly_concatenates_mesh_measurements() -> None:
    path = DATA_DIR / "unit_cube.stl"
    row = measure([path, path])

    assert row.volume is None
    assert row.surface_area == pytest.approx(12.0)
    assert row.base_area == pytest.approx(2.0)
    assert row.is_watertight is False
    assert row.method == "stl-mesh-assembly"
    assert "without boolean union" in "; ".join(row.warnings)


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
    assert row.elapsed_sec is not None


def test_stl_assembly_projects_combined_silhouette_once() -> None:
    path = DATA_DIR / "unit_cube.stl"
    row = project([path, path])

    assert row.projected_area == pytest.approx(1.0)
    assert row.volume is None
    assert row.surface_area == pytest.approx(12.0)
    assert row.base_area == pytest.approx(2.0)
    assert row.method == "stl-mesh-assembly-projection"


def test_non_watertight_stl_leaves_volume_unset() -> None:
    row = measure(
        Path(__file__).parents[1]
        / "samples"
        / "open_cube_missing_face"
        / "open_cube_missing_face_ascii.stl"
    )

    assert row.volume is None
    assert row.surface_area == pytest.approx(5.0)
    assert row.is_watertight is False
    assert "volume is unavailable" in "; ".join(row.warnings)


def test_elapsed_fields_separate_model_loading_from_row_calculation() -> None:
    projected = project(DATA_DIR / "unit_cube.stl")
    rows = sweep(DATA_DIR / "unit_cube.stl", alpha_deg="0:1:1")

    assert projected.load_elapsed_sec is not None
    assert projected.load_elapsed_sec > 0.0
    assert projected.elapsed_sec is not None
    assert projected.elapsed_sec > 0.0
    assert all(row.load_elapsed_sec is not None for row in rows)
    assert all(row.elapsed_sec is not None and row.elapsed_sec > 0.0 for row in rows)


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

    assert checks == 2
    assert completed_rows == []


def test_axis_map_flips_loaded_model_coordinates() -> None:
    row = project(DATA_DIR / "unit_cube.stl", axis_map="-x,y,z")

    assert row.projected_area == pytest.approx(1.0)
    assert row.centroid_x == pytest.approx(-0.5)
    assert row.centroid_y == pytest.approx(0.5)
    assert row.centroid_z == pytest.approx(0.5)
    assert row.x_min == pytest.approx(-1.0)
    assert row.x_max == pytest.approx(0.0)
    assert row.base_area == pytest.approx(1.0)


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


def test_alpha_direction_is_reported_in_model_coordinates() -> None:
    row = project(DATA_DIR / "unit_cube.stl", alpha_deg=60)

    assert row.direction_x == pytest.approx(0.5)
    assert row.direction_y == pytest.approx(0.0)
    assert row.direction_z == pytest.approx(0.8660254037844386)
    assert row.alpha_deg == pytest.approx(60.0)
    assert row.beta_deg == pytest.approx(0.0)
    assert row.roll_deg == pytest.approx(0.0)
    assert row.pitch_deg == pytest.approx(60.0)


def test_vector_direction_reports_equivalent_attitudes() -> None:
    row = project(DATA_DIR / "unit_cube.stl", attitude="vector", direction="0,1,0")

    assert row.direction_x == pytest.approx(0.0)
    assert row.direction_y == pytest.approx(1.0)
    assert row.direction_z == pytest.approx(0.0)
    assert row.alpha_deg == pytest.approx(0.0)
    assert row.beta_deg == pytest.approx(-90.0)
    assert row.roll_deg == pytest.approx(-90.0)
    assert row.pitch_deg == pytest.approx(90.0)


@pytest.mark.parametrize("direction", ["nan,0,0", "inf,0,0", "1,-inf,0"])
def test_vector_direction_rejects_non_finite_components(direction: str) -> None:
    with pytest.raises(ValueError, match="finite"):
        project(DATA_DIR / "unit_cube.stl", attitude="vector", direction=direction)


def test_positive_roll_uses_positive_x_right_hand_rule() -> None:
    row = project(
        DATA_DIR / "unit_cube.stl",
        attitude="roll-pitch",
        roll_deg=90,
        pitch_deg=90,
    )

    assert row.direction_x == pytest.approx(0.0)
    assert row.direction_y == pytest.approx(-1.0)
    assert row.direction_z == pytest.approx(0.0)
    assert row.roll_deg == pytest.approx(90.0)
    assert row.pitch_deg == pytest.approx(90.0)


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
    ("kwargs", "argument"),
    [
        ({"attitude": "alpha-beta", "pitch_deg": 10}, "pitch_deg"),
        ({"attitude": "roll-pitch", "alpha_deg": 10}, "alpha_deg"),
        ({"attitude": "vector", "direction": "1,0,0", "roll_deg": 10}, "roll_deg"),
    ],
)
def test_project_rejects_angles_from_another_attitude(kwargs, argument: str) -> None:
    with pytest.raises(ValueError, match=argument):
        project(DATA_DIR / "unit_cube.stl", **kwargs)


def test_project_requires_direction_for_vector_attitude() -> None:
    with pytest.raises(ValueError, match="direction is required"):
        project(DATA_DIR / "unit_cube.stl", attitude="vector")


def test_project_rejects_unknown_attitude() -> None:
    with pytest.raises(ValueError, match="attitude must be one of"):
        project(DATA_DIR / "unit_cube.stl", attitude="yaw-pitch")


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
