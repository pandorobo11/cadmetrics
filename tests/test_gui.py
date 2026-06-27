from __future__ import annotations

import csv
import importlib
import tomllib
from pathlib import Path

from cadmetrics.gui.export import write_rows_csv
from cadmetrics.gui.jobs import CalculationRequest, run_calculation
from cadmetrics.types import MeasurementRow


def test_gui_entry_point_is_registered() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["cadmetrics-gui"] == "cadmetrics.gui.pyside_app:main"


def test_pyside_gui_module_imports_without_optional_dependencies() -> None:
    module = importlib.import_module("cadmetrics.gui.pyside_app")

    assert module.__name__ == "cadmetrics.gui.pyside_app"


def test_gui_job_delegates_project(monkeypatch) -> None:
    captured = {}
    expected = MeasurementRow(
        file="model.stl",
        input_unit="m",
        output_unit="m",
        roll_deg=1.0,
        alpha_deg=2.0,
        beta_deg=3.0,
        volume=1.0,
        surface_area=2.0,
        projected_area=3.0,
        is_watertight=True,
    )

    def fake_project(path: Path, **kwargs):
        captured["path"] = path
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr("cadmetrics.gui.jobs.project", fake_project)
    request = CalculationRequest(
        file=Path("model.stl"),
        mode="project",
        input_unit="mm",
        output_unit="m",
        roll="1",
        alpha="2",
        beta="3",
        direction="1,0,0",
    )

    assert run_calculation(request) == [expected]
    assert captured["path"] == Path("model.stl")
    assert captured["kwargs"]["roll_deg"] == 1.0
    assert captured["kwargs"]["alpha_deg"] == 2.0
    assert captured["kwargs"]["beta_deg"] == 3.0
    assert captured["kwargs"]["direction"] == "1,0,0"
    assert captured["kwargs"]["input_unit"] == "mm"
    assert captured["kwargs"]["output_unit"] == "m"


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
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "file": "model.stl",
            "input_unit": "m",
            "output_unit": "m",
            "roll_deg": "0.0",
            "alpha_deg": "0.0",
            "beta_deg": "0.0",
            "direction_x": "1.0",
            "direction_y": "0.0",
            "direction_z": "0.0",
            "volume": "1.0",
            "surface_area": "6.0",
            "projected_area": "1.0",
            "is_watertight": "True",
            "mesh_deflection": "0.001",
            "angular_deflection": "0.1",
            "method": "stl-mesh-projection",
            "elapsed_sec": "0.01",
            "warnings": "note",
        }
    ]
