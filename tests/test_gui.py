from __future__ import annotations

import plistlib
import subprocess
import sys
import tomllib
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import trimesh

from cadmetrics.gui.gui_formatters import overlay_text as _overlay_text
from cadmetrics.gui.jobs import CalculationRequest, run_calculation
from cadmetrics.gui.viewer_geometry import base_face_mask as _base_face_mask
from cadmetrics.gui.viewer_geometry import camera_geometry as _camera_geometry
from cadmetrics.gui.viewer_geometry import projection_arrow_geometry as _projection_arrow_geometry
from cadmetrics.gui.viewer_geometry import projection_camera_geometry as _projection_camera_geometry
from cadmetrics.types import MeasurementRow, ModelData


def test_macos_app_uses_project_version(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "scripts/create_macos_app.py",
            "--repo",
            str(Path.cwd()),
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    app = tmp_path / "Cadmetrics.app"
    with (app / "Contents" / "Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert info["CFBundleShortVersionString"] == project["version"]
    assert info["CFBundleVersion"] == project["version"]


def test_projection_arrow_axis_stays_outside_model_and_passes_through_centroid() -> None:
    vertices = np.array([[-1.0, -0.5, -0.5], [1.0, 0.5, 0.5]])
    direction = np.array([1.0, 0.0, 0.0])
    centroid = np.array([0.25, 0.2, -0.1])

    for anchor in (None, centroid):
        start, vector = _projection_arrow_geometry(vertices, direction, through_point=anchor)
        assert start[0] < vertices[:, 0].min()
        assert (start + vector)[0] < vertices[:, 0].min()
        assert vector[0] > 0.0
        if anchor is not None:
            unit_vector = vector / np.linalg.norm(vector)
            assert np.linalg.norm(np.cross(anchor - start, unit_vector)) == pytest.approx(0.0)


def test_base_face_mask_respects_tolerance_and_excludes_new_surfaces() -> None:
    vertices = np.array(
        [
            [1.0, 0.0, 0.0],
            [1.0 - 5.0e-7, 1.0, 0.0],
            [1.0, 0.0, 1.0],
            [1.0 - 5.0e-5, 0.0, -1.0],
            [1.0, -1.0, 0.0],
        ],
    )
    faces = np.array([[0, 1, 2], [0, 2, 3], [0, 2, 4]], dtype=np.int64)

    mask = _base_face_mask(vertices, faces, 1.0e-6, excluded_face_indices=(2,))

    assert mask.tolist() == [True, False, False]


def test_base_face_mask_handles_empty_mesh() -> None:
    mask = _base_face_mask(
        np.empty((0, 3), dtype=float),
        np.empty((0, 3), dtype=np.int64),
        1.0e-6,
    )

    assert mask.size == 0


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


@pytest.mark.parametrize("from_direction", [(1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (-1.0, -1.0, 1.0)])
def test_camera_geometry_looks_from_selected_direction(from_direction) -> None:
    vertices = np.array([[-1.0, -2.0, -3.0], [1.0, 2.0, 3.0]])

    position, focal_point, view_up = _camera_geometry(vertices, np.asarray(from_direction))
    offset = position - focal_point

    assert np.allclose(
        offset / np.linalg.norm(offset), np.asarray(from_direction) / np.linalg.norm(from_direction)
    )
    assert np.dot(view_up, offset) == pytest.approx(0.0)
    assert np.linalg.norm(view_up) == pytest.approx(1.0)


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
        base_area=7.0,
        projected_area=6.0,
        is_watertight=True,
        method="stl-mesh-projection",
    )

    text = _overlay_text(row, model=None, request=None, detailed=True)

    assert "cadmetrics result" in text
    assert "model.stl" in text
    assert "base_area: 7" in text
    assert "projected_area: 6" in text
    assert "roll/pitch: 1, 4 deg" in text
    assert "alpha/beta: 2, 3 deg" in text
    assert "direction: (1, 0, 0)" in text
    assert "centroid: (4, 5, 6)" in text


@pytest.mark.parametrize(
    ("job_request", "engine", "expected_attitude"),
    [
        (
            CalculationRequest(
                file=(Path("body.stl"), Path("wing.stl")),
                input_unit="mm",
                output_unit="m",
                alpha_start=2.0,
                alpha_end=4.0,
                alpha_step=2.0,
                beta_start=-1.0,
                beta_end=1.0,
                beta_step=1.0,
                step_metric_source="mesh",
                step_components=(1, 3),
                step_component_mode="subtract",
            ),
            "sweep_model",
            {"attitude": "alpha-beta", "alpha_deg": "2.0:4.0:2.0", "beta_deg": "-1.0:1.0:1.0"},
        ),
        (
            CalculationRequest(
                file=Path("model.stl"),
                attitude_mode="roll_pitch",
                roll_start=0.0,
                roll_end=10.0,
                roll_step=10.0,
                pitch_start=5.0,
                pitch_end=5.0,
            ),
            "sweep_model",
            {"attitude": "roll-pitch", "roll_deg": "0.0:10.0:10.0", "pitch_deg": "5.0"},
        ),
        (
            CalculationRequest(file=Path("model.stl"), attitude_mode="vector", vector_y=1.0),
            "project_model",
            {"attitude": "vector", "direction": "1.0,1.0,0.0"},
        ),
    ],
    ids=["alpha-beta-assembly", "roll-pitch", "vector"],
)
def test_gui_job_translates_request_to_calculation_api(
    monkeypatch, job_request, engine, expected_attitude
) -> None:
    loaded_model = _model()
    loads = []
    calls = []

    def load(path, options):
        loads.append((path, options))
        return loaded_model

    def calculate(model, **kwargs):
        calls.append((model, kwargs))
        return _row() if engine == "project_model" else [_row()]

    monkeypatch.setattr("cadmetrics.gui.jobs._inspect_model_with_options", load)
    monkeypatch.setattr(f"cadmetrics.gui.jobs.{engine}", calculate)

    rows = run_calculation(job_request)

    assert len(rows) == 1
    assert len(loads) == len(calls) == 1
    assert loads[0][0] == job_request.file
    assert calls[0][0] is loaded_model
    assert {key: calls[0][1][key] for key in expected_attitude} == expected_attitude
    if isinstance(job_request.file, tuple):
        options = loads[0][1]
        assert (options.input_unit, options.output_unit, options.step_metric_source) == (
            "mm",
            "m",
            "mesh",
        )
        assert options.step_components == (1, 3)
        assert options.step_component_mode == "subtract"


def test_gui_job_validates_attitude_before_loading(monkeypatch) -> None:
    def fail_load(*args, **kwargs):
        raise AssertionError("model loading must not run for an invalid attitude")

    monkeypatch.setattr("cadmetrics.gui.jobs._inspect_model_with_options", fail_load)
    request = CalculationRequest(
        file=Path("model.stl"),
        attitude_mode="vector",
        vector_x=0.0,
        vector_y=0.0,
        vector_z=0.0,
    )

    with pytest.raises(ValueError, match="greater than zero"):
        run_calculation(request)


def test_gui_job_uses_loaded_model_without_reloading(monkeypatch) -> None:
    def fail_load(*args, **kwargs):
        raise AssertionError("GUI calculation should not reload the model")

    monkeypatch.setattr("cadmetrics.gui.jobs._inspect_model_with_options", fail_load)
    model = replace(_model(), path=Path("loaded.step"))

    rows = run_calculation(CalculationRequest(file=Path("model.step")), model=model)

    assert len(rows) == 1
    assert rows[0].file == "loaded.step"
    assert rows[0].projected_area == pytest.approx(1.0)


def _row() -> MeasurementRow:
    return MeasurementRow(
        file="model.stl",
        input_unit="m",
        output_unit="m",
        roll_deg=0.0,
        alpha_deg=0.0,
        beta_deg=0.0,
        volume=1.0,
        surface_area=2.0,
        projected_area=3.0,
        is_watertight=True,
    )


def _model() -> ModelData:
    mesh = trimesh.creation.box()
    return ModelData(
        path=Path("model.step"),
        source_format="step",
        vertices=np.asarray(mesh.vertices),
        faces=np.asarray(mesh.faces),
        input_unit="m",
        output_unit="m",
        volume=1.0,
        surface_area=6.0,
        base_area=1.0,
        is_watertight=True,
    )
