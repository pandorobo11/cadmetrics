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
    assert row.method == "stl-mesh-projection"
    assert row.elapsed_sec is not None


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
    assert row.roll_deg == pytest.approx(90.0)
    assert row.pitch_deg == pytest.approx(90.0)
