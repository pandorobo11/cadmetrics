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
