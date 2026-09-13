from dataclasses import replace
from pathlib import Path

import pytest

from cadmetrics.api import inspect_model, measure_model, project_model, sweep_model


@pytest.fixture
def model():
    return replace(
        inspect_model(Path(__file__).parent / "data" / "unit_cube.stl"),
        source_format="step",
        input_unit="mm",
        output_unit="cm",
        volume=None,
        surface_area=None,
        newly_exposed_surface_area=2.5,
        is_watertight=False,
        is_assembly=True,
        component_names=("Body", "Tool", "Tail"),
        selected_components=(1, 3),
        mesh_deflection=0.02,
        angular_deflection=0.15,
        base_tolerance=1e-5,
        step_metric_source="brep",
        step_component_mode="subtract",
        load_elapsed_sec=1.25,
        cadmetrics_version="test-version",
        cadmetrics_hash="test-hash",
        warnings=("volume unavailable", "surface history unavailable"),
    )


@pytest.mark.parametrize(
    "attitude",
    [
        {"alpha_deg": 30.0, "beta_deg": 10.0},
        {"attitude": "roll-pitch", "roll_deg": 20.0, "pitch_deg": 40.0},
        {"attitude": "vector", "direction": "1,2,3"},
    ],
)
def test_measure_project_and_sweep_preserve_model_metadata(model, attitude) -> None:
    measured = measure_model(model)
    projected = project_model(model, **attitude)
    progress = []
    rows = sweep_model(
        model,
        **attitude,
        progress_callback=lambda index, total, row: progress.append((index, total, row)),
    )

    expected = {
        "file": str(model.path),
        "input_unit": "mm",
        "output_unit": "cm",
        "volume": None,
        "surface_area": None,
        "newly_exposed_surface_area": 2.5,
        "base_area": 1.0,
        "is_watertight": False,
        "x_min": 0.0,
        "x_max": 1.0,
        "y_min": 0.0,
        "y_max": 1.0,
        "z_min": 0.0,
        "z_max": 1.0,
        "step_components": "1,3",
        "step_component_names": "Body; Tail",
        "mesh_deflection": 0.02,
        "angular_deflection": 0.15,
        "base_tolerance": 1e-5,
        "step_component_mode": "subtract",
        "load_elapsed_sec": 1.25,
        "cadmetrics_version": "test-version",
        "cadmetrics_hash": "test-hash",
        "warnings": "volume unavailable; surface history unavailable",
    }
    assert len(rows) == 1
    assert progress == [(1, 1, rows[0])]
    for row in (measured, projected, rows[0]):
        serialized = row.to_csv_row()
        assert {key: serialized[key] for key in expected} == expected
    assert measured.method == "step-brep-subtract-assembly"
    assert measured.projected_area is None
    assert measured.direction_x is None
    assert measured.centroid_x is None
    assert projected.method == "step-brep-subtract-assembly+mesh-projection"
    assert replace(projected, elapsed_sec=None) == replace(rows[0], elapsed_sec=None)


@pytest.mark.parametrize("calculate", [measure_model, project_model])
@pytest.mark.parametrize("elapsed_sec", [0.0, 2.5])
def test_model_calculations_preserve_explicit_elapsed_time(model, calculate, elapsed_sec) -> None:
    row = calculate(model, elapsed_sec=elapsed_sec)

    assert row.elapsed_sec == elapsed_sec
    assert row.load_elapsed_sec == 1.25
