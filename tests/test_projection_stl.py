from pathlib import Path

import pytest

pytest.importorskip("shapely")
pytest.importorskip("trimesh")

from cadmetrics.api import measure, project, sweep


DATA_DIR = Path(__file__).parent / "data"


def test_cube_measurements() -> None:
    row = measure(DATA_DIR / "unit_cube.stl")
    assert row.volume == pytest.approx(1.0)
    assert row.surface_area == pytest.approx(6.0)
    assert row.is_watertight is True
    assert row.cadmetrics_version
    assert row.cadmetrics_hash


def test_stl_assembly_concatenates_mesh_measurements() -> None:
    path = DATA_DIR / "unit_cube.stl"
    row = measure([path, path])

    assert row.volume == pytest.approx(2.0)
    assert row.surface_area == pytest.approx(12.0)
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
    assert row.volume == pytest.approx(2.0)
    assert row.surface_area == pytest.approx(12.0)
    assert row.method == "stl-mesh-assembly-projection"


def test_axis_map_flips_loaded_model_coordinates() -> None:
    row = project(DATA_DIR / "unit_cube.stl", axis_map="-x,y,z")

    assert row.projected_area == pytest.approx(1.0)
    assert row.centroid_x == pytest.approx(-0.5)
    assert row.centroid_y == pytest.approx(0.5)
    assert row.centroid_z == pytest.approx(0.5)
    assert row.x_min == pytest.approx(-1.0)
    assert row.x_max == pytest.approx(0.0)


def test_axis_map_rejects_duplicate_source_axes() -> None:
    with pytest.raises(ValueError, match="each source axis exactly once"):
        project(DATA_DIR / "unit_cube.stl", axis_map="x,x,z")


def test_cube_sweep_combinations() -> None:
    rows = sweep(DATA_DIR / "unit_cube.stl", alpha="0:1:1", beta="0:1:1", roll="0")
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
    row = project(DATA_DIR / "unit_cube.stl", direction="0,1,0")

    assert row.direction_x == pytest.approx(0.0)
    assert row.direction_y == pytest.approx(1.0)
    assert row.direction_z == pytest.approx(0.0)
    assert row.alpha_deg == pytest.approx(0.0)
    assert row.beta_deg == pytest.approx(-90.0)
    assert row.roll_deg == pytest.approx(-90.0)
    assert row.pitch_deg == pytest.approx(90.0)


def test_positive_roll_uses_positive_x_right_hand_rule() -> None:
    row = project(DATA_DIR / "unit_cube.stl", roll_deg=90, alpha_deg=90)

    assert row.direction_x == pytest.approx(0.0)
    assert row.direction_y == pytest.approx(-1.0)
    assert row.direction_z == pytest.approx(0.0)
    assert row.roll_deg == pytest.approx(90.0)
    assert row.pitch_deg == pytest.approx(90.0)
