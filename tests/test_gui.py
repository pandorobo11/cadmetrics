from __future__ import annotations

import csv
import importlib
import tomllib
from pathlib import Path

import numpy as np
import pytest

from cadmetrics.gui.export import write_rows_csv
from cadmetrics.gui.jobs import CalculationRequest, run_calculation
from cadmetrics.cli import CSV_FIELDS
from cadmetrics.gui.pyside_app import (
    _default_camera_geometry,
    _overlay_text,
    _projection_arrow_geometry,
    _projection_camera_geometry,
    TABLE_COLUMNS,
)
from cadmetrics.types import MeasurementRow


def test_gui_entry_point_is_registered() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["cadmetrics-gui"] == "cadmetrics.gui.pyside_app:main"
    optional_dependencies = pyproject["project"]["optional-dependencies"]
    assert "gui" in optional_dependencies
    assert "gui-pyside" not in optional_dependencies


def test_pyside_gui_module_imports_without_optional_dependencies() -> None:
    module = importlib.import_module("cadmetrics.gui.pyside_app")

    assert module.__name__ == "cadmetrics.gui.pyside_app"


def test_projection_arrow_stays_outside_model_bounds() -> None:
    vertices = np.array(
        [
            [-1.0, -0.5, -0.5],
            [-1.0, 0.5, 0.5],
            [1.0, -0.5, 0.5],
            [1.0, 0.5, -0.5],
        ],
        dtype=float,
    )
    direction = np.array([1.0, 0.0, 0.0], dtype=float)

    start, vector = _projection_arrow_geometry(vertices, direction)
    end = start + vector

    assert start[0] < vertices[:, 0].min()
    assert end[0] < vertices[:, 0].min()
    assert vector[0] > 0.0


def test_projection_arrow_axis_can_pass_through_centroid_without_entering_model() -> None:
    vertices = np.array(
        [
            [-1.0, -0.5, -0.5],
            [-1.0, 0.5, 0.5],
            [1.0, -0.5, 0.5],
            [1.0, 0.5, -0.5],
        ],
        dtype=float,
    )
    direction = np.array([1.0, 0.0, 0.0], dtype=float)
    centroid = np.array([0.25, 0.2, -0.1], dtype=float)

    start, vector = _projection_arrow_geometry(vertices, direction, through_point=centroid)
    end = start + vector
    unit_vector = vector / np.linalg.norm(vector)
    distance = np.linalg.norm(np.cross(centroid - start, unit_vector))

    assert distance == pytest.approx(0.0)
    assert start[0] < vertices[:, 0].min()
    assert end[0] < vertices[:, 0].min()


def test_gui_viewer_enables_parallel_projection() -> None:
    source = Path("src/cadmetrics/gui/pyside_app.py").read_text(encoding="utf-8")

    assert source.count("enable_parallel_projection()") >= 2


def test_projection_camera_looks_along_direction() -> None:
    vertices = np.array(
        [
            [-1.0, -0.5, -0.5],
            [-1.0, 0.5, 0.5],
            [1.0, -0.5, 0.5],
            [1.0, 0.5, -0.5],
        ],
        dtype=float,
    )
    direction = np.array([1.0, 0.0, 0.0], dtype=float)

    position, focal_point, view_up = _projection_camera_geometry(vertices, direction)
    view_direction = (focal_point - position) / np.linalg.norm(focal_point - position)

    assert np.allclose(view_direction, direction)
    assert np.isclose(float(np.dot(view_up, direction)), 0.0)


def test_default_camera_is_from_negative_x_negative_y_positive_z() -> None:
    vertices = np.array(
        [
            [-1.0, -0.5, -0.5],
            [-1.0, 0.5, 0.5],
            [1.0, -0.5, 0.5],
            [1.0, 0.5, -0.5],
        ],
        dtype=float,
    )

    position, focal_point, view_up = _default_camera_geometry(vertices)
    offset = position - focal_point

    assert offset[0] < 0.0
    assert offset[1] < 0.0
    assert offset[2] > 0.0
    assert np.isclose(float(np.dot(view_up, focal_point - position)), 0.0)


def test_overlay_text_includes_selected_result_values() -> None:
    row = MeasurementRow(
        file="/tmp/model.stl",
        input_unit="mm",
        output_unit="m",
        roll_deg=1.0,
        pitch_deg=4.0,
        alpha_deg=2.0,
        beta_deg=3.0,
        direction_x=1.0,
        direction_y=0.0,
        direction_z=0.0,
        centroid_u=2.0,
        centroid_v=3.0,
        centroid_x=4.0,
        centroid_y=5.0,
        centroid_z=6.0,
        volume=4.0,
        surface_area=5.0,
        projected_area=6.0,
        is_watertight=True,
        method="stl-mesh-projection",
    )

    text = _overlay_text(row, model=None, request=None)

    assert "cadmetrics result" in text
    assert "model.stl" in text
    assert "projected_area: 6" in text
    assert "roll/pitch: 1, 4 deg" in text
    assert "alpha/beta: 2, 3 deg" in text
    assert "direction: (1, 0, 0)" in text
    assert "centroid: (4, 5, 6)" in text


def test_gui_view_can_be_saved_as_image() -> None:
    source = Path("src/cadmetrics/gui/pyside_app.py").read_text(encoding="utf-8")

    assert "screenshot(str(output_path))" in source


def test_gui_job_delegates_alpha_beta_sweep(monkeypatch) -> None:
    captured = {}
    expected = [_row()]

    def fake_sweep(path: Path, **kwargs):
        captured["path"] = path
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr("cadmetrics.gui.jobs.sweep", fake_sweep)
    request = CalculationRequest(
        file=Path("model.stl"),
        attitude_mode="alpha_beta",
        input_unit="mm",
        output_unit="m",
        alpha_start=2.0,
        alpha_end=4.0,
        alpha_step=2.0,
        beta_start=-1.0,
        beta_end=1.0,
        beta_step=1.0,
    )

    assert run_calculation(request) == expected
    assert captured["path"] == Path("model.stl")
    assert captured["kwargs"]["roll"] == 0.0
    assert captured["kwargs"]["alpha"] == "2.0:4.0:2.0"
    assert captured["kwargs"]["beta"] == "-1.0:1.0:1.0"
    assert captured["kwargs"]["input_unit"] == "mm"
    assert captured["kwargs"]["output_unit"] == "m"


def test_gui_job_delegates_roll_pitch_sweep(monkeypatch) -> None:
    captured = {}
    expected = [_row()]

    def fake_sweep(path: Path, **kwargs):
        captured["path"] = path
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr("cadmetrics.gui.jobs.sweep", fake_sweep)
    request = CalculationRequest(
        file=Path("model.stl"),
        attitude_mode="roll_pitch",
        roll_start=0.0,
        roll_end=10.0,
        roll_step=10.0,
        pitch_start=5.0,
        pitch_end=5.0,
        pitch_step=1.0,
    )

    assert run_calculation(request) == expected
    assert captured["kwargs"]["roll"] == "0.0:10.0:10.0"
    assert captured["kwargs"]["alpha"] == "5.0"
    assert captured["kwargs"]["beta"] == 0.0


def test_gui_job_delegates_single_vector(monkeypatch) -> None:
    captured = []

    def fake_project(path: Path, **kwargs):
        captured.append((path, kwargs))
        return _row(direction=kwargs["direction"])

    monkeypatch.setattr("cadmetrics.gui.jobs.project", fake_project)
    request = CalculationRequest(
        file=Path("model.stl"),
        attitude_mode="vector",
        vector_x=1.0,
        vector_y=1.0,
        vector_z=0.0,
    )

    rows = run_calculation(request)

    assert len(rows) == 1
    assert [kwargs["direction"] for _, kwargs in captured] == ["1.0,1.0,0.0"]


def test_gui_csv_export_matches_cli_columns(tmp_path: Path) -> None:
    output = tmp_path / "rows.csv"
    row = MeasurementRow(
        file="model.stl",
        input_unit="m",
        output_unit="m",
        roll_deg=0.0,
        alpha_deg=0.0,
        beta_deg=0.0,
        direction_x=1.0,
        direction_y=0.0,
        direction_z=0.0,
        centroid_u=0.0,
        centroid_v=0.0,
        centroid_x=0.0,
        centroid_y=0.0,
        centroid_z=0.0,
        x_min=0.0,
        x_max=1.0,
        y_min=0.0,
        y_max=1.0,
        z_min=0.0,
        z_max=1.0,
        volume=1.0,
        surface_area=6.0,
        projected_area=1.0,
        is_watertight=True,
        mesh_deflection=0.001,
        angular_deflection=0.1,
        method="stl-mesh-projection",
        elapsed_sec=0.01,
        warnings=("note",),
    )

    write_rows_csv(output, [row])

    with output.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == CSV_FIELDS
    assert rows == [
        {
            "file": "model.stl",
            "input_unit": "m",
            "output_unit": "m",
            "roll_deg": "0.0",
            "pitch_deg": "",
            "alpha_deg": "0.0",
            "beta_deg": "0.0",
            "direction_x": "1.0",
            "direction_y": "0.0",
            "direction_z": "0.0",
            "x_min": "0.0",
            "x_max": "1.0",
            "y_min": "0.0",
            "y_max": "1.0",
            "z_min": "0.0",
            "z_max": "1.0",
            "surface_area": "6.0",
            "volume": "1.0",
            "projected_area": "1.0",
            "centroid_u": "0.0",
            "centroid_v": "0.0",
            "centroid_x": "0.0",
            "centroid_y": "0.0",
            "centroid_z": "0.0",
            "is_watertight": "True",
            "mesh_deflection": "0.001",
            "angular_deflection": "0.1",
            "method": "stl-mesh-projection",
            "elapsed_sec": "0.01",
            "warnings": "note",
        }
    ]


def test_gui_table_columns_match_cli_order() -> None:
    assert TABLE_COLUMNS == CSV_FIELDS


def _row(*, direction: str | None = None) -> MeasurementRow:
    return MeasurementRow(
        file="model.stl",
        input_unit="m",
        output_unit="m",
        roll_deg=0.0,
        alpha_deg=0.0,
        beta_deg=0.0,
        direction_x=1.0 if direction is not None else None,
        direction_y=0.0 if direction is not None else None,
        direction_z=0.0 if direction is not None else None,
        volume=1.0,
        surface_area=2.0,
        projected_area=3.0,
        is_watertight=True,
    )
