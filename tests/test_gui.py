from __future__ import annotations

import csv
import importlib
import plistlib
import subprocess
import sys
import tomllib
from pathlib import Path

import numpy as np
import pytest

from cadmetrics.gui.export import write_rows_csv
from cadmetrics.gui.control_panel import CAMERA_DIRECTIONS
from cadmetrics.gui.gui_formatters import (
    component_display_groups as _component_display_groups,
    format_file_selection as _format_file_selection,
    format_model_file_label as _format_model_file_label,
    overlay_text as _overlay_text,
)
from cadmetrics.gui.jobs import CalculationRequest, run_calculation
from cadmetrics.cli import CSV_FIELDS
from cadmetrics.gui.viewer_geometry import camera_geometry as _camera_geometry
from cadmetrics.gui.viewer_geometry import base_face_mask as _base_face_mask
from cadmetrics.gui.viewer_geometry import default_camera_geometry as _default_camera_geometry
from cadmetrics.gui.viewer_geometry import projection_arrow_geometry as _projection_arrow_geometry
from cadmetrics.gui.viewer_geometry import projection_camera_geometry as _projection_camera_geometry
from cadmetrics.types import MeasurementRow, ModelData


def test_gui_entry_point_is_registered() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["cadmetrics-gui"] == "cadmetrics.gui.pyside_app:main"
    optional_dependencies = pyproject["project"]["optional-dependencies"]
    assert "gui" in optional_dependencies
    assert "gui-pyside" not in optional_dependencies


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


def test_pyside_gui_module_imports_without_optional_dependencies() -> None:
    module = importlib.import_module("cadmetrics.gui.pyside_app")

    assert module.__name__ == "cadmetrics.gui.pyside_app"


def test_gui_opens_mkdocs_site_in_default_browser() -> None:
    source = Path("src/cadmetrics/gui/pyside_app.py").read_text(encoding="utf-8")

    assert 'addMenu("Help")' in source
    assert 'QAction("Documentation"' in source
    assert "self._documentation_index is None" in source
    assert "build_documentation_site(parent, site_dir)" in source
    assert "QDesktopServices.openUrl(url)" in source


def test_build_hook_bundles_documentation() -> None:
    source = Path("hatch_build.py").read_text(encoding="utf-8")

    assert '"cadmetrics/_docs_site"' in source
    assert "build_documentation_site(root, docs_site)" in source


def test_release_workflow_packages_html_documentation() -> None:
    source = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "cd .hatch-build/cadmetrics-docs-site" in source
    assert 'cadmetrics-docs-${GITHUB_REF_NAME}.zip' in source
    assert "dist/cadmetrics-docs-*.zip" in source


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


def test_base_face_mask_selects_only_xmax_triangles() -> None:
    vertices = np.array(
        [
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [1.0, 0.0, 1.0],
            [0.0, 0.0, 0.0],
        ],
        dtype=float,
    )
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)

    mask = _base_face_mask(vertices, faces, 1.0e-6)

    assert mask.tolist() == [True, False]


def test_base_face_mask_uses_relative_tolerance() -> None:
    vertices = np.array(
        [
            [1.0, 0.0, 0.0],
            [1.0 - 5.0e-7, 1.0, 0.0],
            [1.0, 0.0, 1.0],
            [1.0 - 5.0e-5, 0.0, -1.0],
        ],
        dtype=float,
    )
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)

    mask = _base_face_mask(vertices, faces, 1.0e-6)

    assert mask.tolist() == [True, False]


def test_base_face_mask_handles_empty_mesh() -> None:
    mask = _base_face_mask(
        np.empty((0, 3), dtype=float),
        np.empty((0, 3), dtype=np.int64),
        1.0e-6,
    )

    assert mask.size == 0


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
    source = Path("src/cadmetrics/gui/viewer.py").read_text(encoding="utf-8")

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


@pytest.mark.parametrize(("label", "from_direction"), CAMERA_DIRECTIONS)
def test_camera_geometry_looks_from_selected_direction(label, from_direction) -> None:
    vertices = np.array([[-1.0, -2.0, -3.0], [1.0, 2.0, 3.0]], dtype=float)

    position, focal_point, view_up = _camera_geometry(
        vertices,
        np.asarray(from_direction, dtype=float),
    )
    actual_from_direction = (position - focal_point) / np.linalg.norm(position - focal_point)
    expected_from_direction = np.asarray(from_direction) / np.linalg.norm(from_direction)

    assert label
    assert np.allclose(actual_from_direction, expected_from_direction)
    assert np.isclose(float(np.dot(view_up, focal_point - position)), 0.0)
    assert np.isclose(float(np.linalg.norm(view_up)), 1.0)


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

    text = _overlay_text(row, model=None, request=None)

    assert "cadmetrics result" in text
    assert "model.stl" in text
    assert "base_area: 7" in text
    assert "projected_area: 6" in text
    assert "roll/pitch: 1, 4 deg" in text
    assert "alpha/beta: 2, 3 deg" in text
    assert "direction: (1, 0, 0)" in text
    assert "centroid: (4, 5, 6)" in text


def test_gui_view_can_be_saved_as_image() -> None:
    source = Path("src/cadmetrics/gui/viewer.py").read_text(encoding="utf-8")

    assert "screenshot(str(output))" in source


def test_projection_arrow_display_can_be_toggled() -> None:
    controls = Path("src/cadmetrics/gui/control_panel.py").read_text(encoding="utf-8")
    viewer = Path("src/cadmetrics/gui/viewer.py").read_text(encoding="utf-8")

    assert 'self._check("Projection arrow", True)' in controls
    assert "if self._options.show_projection_arrow:" in viewer


def test_base_face_highlight_can_be_toggled() -> None:
    controls = Path("src/cadmetrics/gui/control_panel.py").read_text(encoding="utf-8")
    app = Path("src/cadmetrics/gui/pyside_app.py").read_text(encoding="utf-8")

    assert 'self._check("Base face", False)' in controls
    assert "show_base_face.setChecked(False)" in app
    assert "No Xmax base face found." in app


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
        step_metric_source="mesh",
        step_components=(1, 3),
    )

    assert run_calculation(request) == expected
    assert captured["path"] == Path("model.stl")
    assert captured["kwargs"]["roll"] == 0.0
    assert captured["kwargs"]["alpha"] == "2.0:4.0:2.0"
    assert captured["kwargs"]["beta"] == "-1.0:1.0:1.0"
    assert captured["kwargs"]["input_unit"] == "mm"
    assert captured["kwargs"]["output_unit"] == "m"
    assert captured["kwargs"]["step_metric_source"] == "mesh"
    assert captured["kwargs"]["step_components"] == (1, 3)


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


def test_gui_job_passes_multiple_files_as_one_assembly(monkeypatch) -> None:
    captured = {}
    paths = (Path("body.stl"), Path("wing.stl"))

    def fake_sweep(path, **kwargs):
        captured["path"] = path
        captured["kwargs"] = kwargs
        return [_row()]

    monkeypatch.setattr("cadmetrics.gui.jobs.sweep", fake_sweep)
    request = CalculationRequest(
        file=paths,
        attitude_mode="alpha_beta",
        alpha_start=0.0,
        alpha_end=0.0,
        beta_start=0.0,
        beta_end=0.0,
        step_components=(2,),
    )

    assert run_calculation(request) == [_row()]
    assert captured["path"] == paths
    assert captured["kwargs"]["step_components"] == (2,)


def test_gui_job_uses_loaded_model_without_reloading(monkeypatch) -> None:
    def fail_sweep(*args, **kwargs):
        raise AssertionError("GUI calculation should reuse the loaded model")

    monkeypatch.setattr("cadmetrics.gui.jobs.sweep", fail_sweep)
    model = ModelData(
        path=Path("loaded.step"),
        source_format="step",
        vertices=np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [1.0, 0.0, 1.0],
                [1.0, 1.0, 1.0],
                [0.0, 1.0, 1.0],
            ],
            dtype=float,
        ),
        faces=np.array(
            [
                [0, 1, 2],
                [0, 2, 3],
                [4, 6, 5],
                [4, 7, 6],
                [0, 4, 5],
                [0, 5, 1],
                [1, 5, 6],
                [1, 6, 2],
                [2, 6, 7],
                [2, 7, 3],
                [3, 7, 4],
                [3, 4, 0],
            ],
            dtype=np.int64,
        ),
        input_unit="m",
        output_unit="m",
        volume=1.0,
        surface_area=6.0,
        base_area=1.0,
        is_watertight=True,
        mesh_deflection=0.001,
        angular_deflection=0.1,
        step_metric_source="brep",
    )
    request = CalculationRequest(
        file=Path("model.step"),
        attitude_mode="alpha_beta",
        alpha_start=0.0,
        alpha_end=0.0,
        beta_start=0.0,
        beta_end=0.0,
    )

    rows = run_calculation(request, model=model)

    assert len(rows) == 1
    assert rows[0].file == "loaded.step"
    assert rows[0].projected_area == pytest.approx(1.0)


def test_gui_formats_multiple_file_selection_labels() -> None:
    paths = (Path("/tmp/body.step"), Path("/tmp/wing.step"), Path("/tmp/tail.step"))

    assert _format_file_selection(paths) == "body.step + 2 more"
    assert _format_model_file_label(Path("; ".join(str(path) for path in paths))) == (
        "body.step + wing.step + tail.step"
    )


def test_gui_groups_multi_file_step_components_by_file() -> None:
    groups = _component_display_groups(
        (
            "body.step: Component 1",
            "body.step: Component 2",
            "wing.step: Component 1",
        ),
        grouped=True,
    )

    assert groups == [
        ("body.step", [(1, "Component 1"), (2, "Component 2")]),
        ("wing.step", [(3, "Component 1")]),
    ]


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
        base_area=1.0,
        projected_area=1.0,
        is_watertight=True,
        mesh_deflection=0.001,
        angular_deflection=0.1,
        base_tolerance=1.0e-6,
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
            "step_components": "",
            "step_component_names": "",
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
            "base_area": "1.0",
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
            "base_tolerance": "1e-06",
            "method": "stl-mesh-projection",
            "elapsed_sec": "0.01",
            "cadmetrics_version": row.cadmetrics_version,
            "cadmetrics_hash": row.cadmetrics_hash,
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


def _model() -> ModelData:
    return ModelData(
        path=Path("model.step"),
        source_format="step",
        vertices=np.empty((0, 3), dtype=float),
        faces=np.empty((0, 3), dtype=np.int64),
        input_unit="m",
        output_unit="m",
        volume=1.0,
        surface_area=6.0,
        base_area=1.0,
        is_watertight=True,
    )
