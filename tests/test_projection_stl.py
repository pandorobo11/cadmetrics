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


def test_cube_sweep_combinations() -> None:
    rows = sweep(DATA_DIR / "unit_cube.stl", alpha="0:1:1", beta="0:1:1", roll="0")
    assert len(rows) == 4
    assert all(row.projected_area is not None for row in rows)
