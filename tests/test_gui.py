from __future__ import annotations

import os
import importlib
import plistlib
import shlex
import subprocess
import sys
import tomllib
import types
from contextlib import ExitStack
from pathlib import Path

import numpy as np
import pytest
from PySide6 import QtWidgets

from cadmetrics.gui.export import write_rows_csv
from cadmetrics.gui.control_panel import CAMERA_DIRECTIONS
from cadmetrics.gui.control_panel import ControlPanel
from cadmetrics.gui.gui_formatters import (
    component_display_groups as _component_display_groups,
    format_file_selection as _format_file_selection,
    format_model_file_label as _format_model_file_label,
    overlay_text as _overlay_text,
)
from cadmetrics.gui.gui_types import ViewerOptions
from cadmetrics.gui.jobs import CalculationRequest, run_calculation
from cadmetrics.result_schema import RESULT_FIELD_SPECS
from cadmetrics.gui.viewer import ModelViewer
from cadmetrics.gui.viewer_geometry import camera_geometry as _camera_geometry
from cadmetrics.gui.viewer_geometry import base_face_mask as _base_face_mask
from cadmetrics.gui.viewer_geometry import default_camera_geometry as _default_camera_geometry
from cadmetrics.gui.viewer_geometry import projection_arrow_geometry as _projection_arrow_geometry
from cadmetrics.gui.viewer_geometry import projection_camera_geometry as _projection_camera_geometry
from cadmetrics.types import MeasurementRow, ModelData


class _RecordingPlotter(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.parallel_projection_calls = 0
        self.arrow_calls = []
        self.mesh_calls = []
        self.removed_actors = []
        self.screenshot_paths = []
        self.camera_position = None

    def set_background(self, color: str) -> None:
        pass

    def remove_all_lights(self) -> None:
        pass

    def add_light(self, light) -> None:
        pass

    def enable_lightkit(self) -> None:
        pass

    def add_axes(self) -> None:
        pass

    def show_grid(self) -> None:
        pass

    def enable_parallel_projection(self) -> None:
        self.parallel_projection_calls += 1

    def reset_camera(self) -> None:
        pass

    def reset_camera_clipping_range(self) -> None:
        pass

    def render(self) -> None:
        pass

    def add_arrows(self, start, vector, **kwargs):
        actor = object()
        self.arrow_calls.append((start, vector, kwargs, actor))
        return actor

    def add_mesh(self, mesh, **kwargs):
        actor = object()
        self.mesh_calls.append((mesh, kwargs, actor))
        return actor

    def add_text(self, text: str, **kwargs):
        return object()

    def remove_actor(self, actor) -> None:
        self.removed_actors.append(actor)

    def screenshot(self, path: str) -> None:
        self.screenshot_paths.append(path)


def _workflow_step(path: Path, *, job: str, name: str):
    yaml = pytest.importorskip("yaml")
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    return next(step for step in workflow["jobs"][job]["steps"] if step.get("name") == name)


def _shell_commands(script: str) -> list[list[str]]:
    return [shlex.split(line) for line in script.splitlines() if line.strip()]


def _viewer_model() -> ModelData:
    return ModelData(
        path=Path("model.step"),
        source_format="step",
        vertices=np.array(
            [[-1.0, -0.5, -0.5], [-1.0, 0.5, 0.5], [1.0, -0.5, 0.5], [1.0, 0.5, -0.5]],
            dtype=float,
        ),
        faces=np.empty((0, 3), dtype=np.int64),
        input_unit="m",
        output_unit="m",
        volume=1.0,
        surface_area=6.0,
        base_area=1.0,
        is_watertight=True,
    )


def test_gui_entry_point_is_registered() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert "cadmetrics-gui" not in pyproject["project"]["scripts"]
    assert pyproject["project"]["gui-scripts"]["cadmetrics-gui"] == (
        "cadmetrics.gui.pyside_app:main"
    )
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


def test_gui_documentation_action_opens_cached_local_site(
    qtbot, monkeypatch, tmp_path: Path
) -> None:
    import cadmetrics.gui.pyside_app as pyside_app

    index = tmp_path / "site" / "index.html"
    index.parent.mkdir()
    index.touch()
    site_build_calls = []
    opened_urls = []

    def fake_site_index(stack: ExitStack):
        site_build_calls.append(stack)
        return index, None

    def fake_open_url(url) -> bool:
        opened_urls.append(url)
        return True

    monkeypatch.setattr(pyside_app, "_documentation_site_index", fake_site_index)
    monkeypatch.setattr(pyside_app.QtGui.QDesktopServices, "openUrl", fake_open_url)

    class DocumentationWindow(QtWidgets.QMainWindow):
        _show_documentation = pyside_app.MainWindow._show_documentation

        def __init__(self) -> None:
            super().__init__()
            self._documentation_resources = ExitStack()
            self._documentation_index = None
            self._documentation_tempdir = None
            self.errors = []

        def _show_error(self, message: str) -> None:
            self.errors.append(message)

    window = DocumentationWindow()
    qtbot.addWidget(window)
    pyside_app.MainWindow._build_menu(window)
    menu_bar = window.menuBar()
    help_action = next(action for action in menu_bar.actions() if action.text() == "Help")
    help_menu = help_action.menu()
    assert help_menu is not None
    documentation_action = next(
        action for action in help_menu.actions() if action.text() == "Documentation"
    )

    documentation_action.trigger()
    documentation_action.trigger()

    assert site_build_calls == [window._documentation_resources]
    assert [url.toLocalFile() for url in opened_urls] == [str(index), str(index)]
    assert window.errors == []
    window._documentation_resources.close()


def test_gui_documentation_index_builds_site_from_source_tree(
    monkeypatch, tmp_path: Path
) -> None:
    import cadmetrics.gui.pyside_app as pyside_app

    project_root = tmp_path / "project"
    source_file = project_root / "src" / "cadmetrics" / "gui" / "pyside_app.py"
    source_file.parent.mkdir(parents=True)
    source_file.touch()
    (project_root / "README.md").touch()
    (project_root / "docs").mkdir()
    build_calls = []

    def fake_build(root: Path, site_dir: Path) -> None:
        build_calls.append((root, site_dir))
        site_dir.mkdir(parents=True)
        (site_dir / "index.html").touch()

    monkeypatch.setattr(pyside_app, "__file__", str(source_file))
    monkeypatch.setattr(pyside_app, "build_documentation_site", fake_build)

    with ExitStack() as resources:
        index, temporary = pyside_app._documentation_site_index(resources)
        assert temporary is not None
        assert build_calls == [(project_root, index.parent)]
        assert index.is_file()
        temporary.cleanup()


def test_build_hook_bundles_generated_documentation(monkeypatch, tmp_path: Path) -> None:
    package_names = (
        "hatchling",
        "hatchling.builders",
        "hatchling.builders.hooks",
        "hatchling.builders.hooks.plugin",
    )
    for package_name in package_names:
        package = types.ModuleType(package_name)
        package.__path__ = []
        monkeypatch.setitem(sys.modules, package_name, package)
    interface = types.ModuleType("hatchling.builders.hooks.plugin.interface")
    interface.BuildHookInterface = type("BuildHookInterface", (), {})
    monkeypatch.setitem(sys.modules, interface.__name__, interface)

    spec = importlib.util.spec_from_file_location("cadmetrics_test_hatch_build", "hatch_build.py")
    assert spec is not None and spec.loader is not None
    hatch_build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hatch_build)
    build_calls = []
    monkeypatch.setattr(
        hatch_build,
        "_load_docs_builder",
        lambda path: types.SimpleNamespace(
            build_documentation_site=lambda root, site: build_calls.append((root, site))
        ),
    )
    monkeypatch.setattr(hatch_build, "_git_hash", lambda root: "abc123")

    hook = hatch_build.CustomBuildHook()
    hook.root = str(tmp_path)
    hook.target_name = "wheel"
    build_data = {}

    hook.initialize("0.0.0", build_data)

    docs_site = tmp_path / ".hatch-build" / "cadmetrics-docs-site"
    assert build_calls == [(tmp_path, docs_site)]
    assert build_data["force_include"][str(docs_site)] == "cadmetrics/_docs_site"


def test_release_workflow_packages_html_documentation() -> None:
    package_step = _workflow_step(
        Path(".github/workflows/release.yml"),
        job="release",
        name="Package HTML documentation",
    )
    commands = _shell_commands(package_step["run"])
    assert commands[0] == ["cd", ".hatch-build/cadmetrics-docs-site"]
    assert commands[1][0:2] == ["zip", "-r"]
    assert commands[1][2] == "../../dist/cadmetrics-docs-${GITHUB_REF_NAME}.zip"
    assert commands[1][3:] == ["."]

    release_step = _workflow_step(
        Path(".github/workflows/release.yml"),
        job="release",
        name="Create GitHub Release",
    )
    release_files = set(release_step["with"]["files"].splitlines())
    assert "dist/cadmetrics-docs-*.zip" in release_files


def test_package_workflows_run_installed_gui_smoke() -> None:
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [sys.executable, "scripts/smoke_gui.py"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert "GUI window smoke passed:" in completed.stdout

    for workflow_path, job in (
        (Path(".github/workflows/ci.yml"), "package"),
        (Path(".github/workflows/release.yml"), "release"),
    ):
        step = _workflow_step(workflow_path, job=job, name="Smoke install gui extra")
        assert step["env"]["QT_QPA_PLATFORM"] == "offscreen"
        commands = _shell_commands(step["run"])
        smoke_command = next(
            command for command in commands if command[-1] == "scripts/smoke_gui.py"
        )
        assert Path(smoke_command[0]).name == "python"


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


def test_base_face_mask_excludes_newly_exposed_triangles() -> None:
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

    mask = _base_face_mask(vertices, faces, 1.0e-6, (0,))

    assert mask.tolist() == [False, False]


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


def test_gui_viewer_keeps_parallel_projection_when_camera_changes(qtbot) -> None:
    plotters = []

    def factory(parent: QtWidgets.QWidget) -> _RecordingPlotter:
        plotter = _RecordingPlotter(parent)
        plotters.append(plotter)
        return plotter

    viewer = ModelViewer(plotter_factory=factory)
    qtbot.addWidget(viewer)
    plotter = plotters[0]

    assert plotter.parallel_projection_calls == 1

    viewer._model = _viewer_model()
    viewer.set_camera((1.0, 0.0, 0.0))

    assert plotter.parallel_projection_calls == 2
    assert plotter.camera_position is not None


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

    text = _overlay_text(row, model=None, request=None, detailed=True)

    assert "cadmetrics result" in text
    assert "model.stl" in text
    assert "base_area: 7" in text
    assert "projected_area: 6" in text
    assert "roll/pitch: 1, 4 deg" in text
    assert "alpha/beta: 2, 3 deg" in text
    assert "direction: (1, 0, 0)" in text
    assert "centroid: (4, 5, 6)" in text


def test_gui_view_can_be_saved_as_image(qtbot, tmp_path: Path) -> None:
    plotters = []

    def factory(parent: QtWidgets.QWidget) -> _RecordingPlotter:
        plotter = _RecordingPlotter(parent)
        plotters.append(plotter)
        return plotter

    viewer = ModelViewer(plotter_factory=factory)
    qtbot.addWidget(viewer)

    output = viewer.save_image(tmp_path / "view")

    assert output == tmp_path / "view.png"
    assert plotters[0].screenshot_paths == [str(output)]


def test_projection_arrow_display_can_be_toggled(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)
    assert panel.viewer_options().show_projection_arrow is True
    panel.show_projection_arrow.setChecked(False)
    assert panel.viewer_options().show_projection_arrow is False

    plotters = []

    def factory(parent: QtWidgets.QWidget) -> _RecordingPlotter:
        plotter = _RecordingPlotter(parent)
        plotters.append(plotter)
        return plotter

    viewer = ModelViewer(plotter_factory=factory)
    qtbot.addWidget(viewer)
    viewer._model = _viewer_model()
    viewer.set_options(
        ViewerOptions(show_projection_arrow=True, show_centroid=False, show_overlay=False)
    )
    arrow_actor = plotters[0].arrow_calls[-1][3]

    viewer.set_options(
        ViewerOptions(show_projection_arrow=False, show_centroid=False, show_overlay=False)
    )

    assert len(plotters[0].arrow_calls) == 1
    assert arrow_actor in plotters[0].removed_actors


def test_base_face_highlight_can_be_toggled(qtbot) -> None:
    import cadmetrics.gui.pyside_app as pyside_app

    panel = ControlPanel()
    qtbot.addWidget(panel)

    class WindowHarness:
        controls = panel

    harness = WindowHarness()
    pyside_app.MainWindow._set_base_face_available(harness, True)
    assert panel.show_base_face.isEnabled() is True
    panel.show_base_face.setChecked(True)
    assert panel.viewer_options().show_base_face is True

    pyside_app.MainWindow._set_base_face_available(harness, False)
    assert panel.show_base_face.isEnabled() is False
    assert panel.show_base_face.isChecked() is False
    assert "No Xmax base face" in panel.show_base_face.toolTip()

    plotters = []

    def factory(parent: QtWidgets.QWidget) -> _RecordingPlotter:
        plotter = _RecordingPlotter(parent)
        plotters.append(plotter)
        return plotter

    viewer = ModelViewer(plotter_factory=factory)
    qtbot.addWidget(viewer)
    base_face = object()
    viewer._base_face_polydata = base_face
    viewer.set_options(ViewerOptions(show_base_face=True))
    base_face_actor = plotters[0].mesh_calls[-1][2]
    assert plotters[0].mesh_calls[-1][0] is base_face

    viewer.set_options(ViewerOptions(show_base_face=False))
    assert base_face_actor in plotters[0].removed_actors


def test_gui_job_delegates_alpha_beta_sweep(monkeypatch) -> None:
    captured = {}
    expected = [_row()]
    loaded_model = _model()

    def fake_load(path: Path, options):
        captured["path"] = path
        captured["options"] = options
        return loaded_model

    def fake_sweep(model: ModelData, **kwargs):
        captured["model"] = model
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr("cadmetrics.gui.jobs._inspect_model_with_options", fake_load)
    monkeypatch.setattr("cadmetrics.gui.jobs.sweep_model", fake_sweep)
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
        step_component_mode="subtract",
    )

    assert run_calculation(request) == expected
    assert captured["path"] == Path("model.stl")
    assert captured["model"] is loaded_model
    assert captured["kwargs"]["attitude"] == "alpha-beta"
    assert captured["kwargs"]["alpha_deg"] == "2.0:4.0:2.0"
    assert captured["kwargs"]["beta_deg"] == "-1.0:1.0:1.0"
    assert captured["options"].input_unit == "mm"
    assert captured["options"].output_unit == "m"
    assert captured["options"].step_metric_source == "mesh"
    assert captured["options"].step_components == (1, 3)
    assert captured["options"].step_component_mode == "subtract"


def test_gui_job_delegates_roll_pitch_sweep(monkeypatch) -> None:
    captured = {}
    expected = [_row()]
    loaded_model = _model()

    def fake_load(path: Path, options):
        captured["path"] = path
        captured["options"] = options
        return loaded_model

    def fake_sweep(model: ModelData, **kwargs):
        captured["model"] = model
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr("cadmetrics.gui.jobs._inspect_model_with_options", fake_load)
    monkeypatch.setattr("cadmetrics.gui.jobs.sweep_model", fake_sweep)
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
    assert captured["path"] == Path("model.stl")
    assert captured["model"] is loaded_model
    assert captured["kwargs"]["attitude"] == "roll-pitch"
    assert captured["kwargs"]["roll_deg"] == "0.0:10.0:10.0"
    assert captured["kwargs"]["pitch_deg"] == "5.0"


def test_gui_job_delegates_single_vector(monkeypatch) -> None:
    captured = []
    loaded_model = _model()

    def fake_load(path: Path, options):
        captured.append(("load", path, options))
        return loaded_model

    def fake_project(model: ModelData, **kwargs):
        captured.append(("project", model, kwargs))
        return _row(direction=kwargs["direction"])

    monkeypatch.setattr("cadmetrics.gui.jobs._inspect_model_with_options", fake_load)
    monkeypatch.setattr("cadmetrics.gui.jobs.project_model", fake_project)
    request = CalculationRequest(
        file=Path("model.stl"),
        attitude_mode="vector",
        vector_x=1.0,
        vector_y=1.0,
        vector_z=0.0,
    )

    rows = run_calculation(request)

    assert len(rows) == 1
    assert captured[0][0:2] == ("load", Path("model.stl"))
    assert captured[1][0:2] == ("project", loaded_model)
    assert captured[1][2]["attitude"] == "vector"
    assert captured[1][2]["direction"] == "1.0,1.0,0.0"


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


def test_gui_job_passes_multiple_files_as_one_assembly(monkeypatch) -> None:
    captured = {}
    paths = (Path("body.stl"), Path("wing.stl"))
    loaded_model = _model()

    def fake_load(path, options):
        captured["path"] = path
        captured["options"] = options
        return loaded_model

    def fake_sweep(model, **kwargs):
        captured["model"] = model
        captured["kwargs"] = kwargs
        return [_row()]

    monkeypatch.setattr("cadmetrics.gui.jobs._inspect_model_with_options", fake_load)
    monkeypatch.setattr("cadmetrics.gui.jobs.sweep_model", fake_sweep)
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
    assert captured["model"] is loaded_model
    assert captured["options"].step_components == (2,)


def test_gui_job_uses_loaded_model_without_reloading(monkeypatch) -> None:
    def fail_load(*args, **kwargs):
        raise AssertionError("GUI calculation should not reload the model")

    monkeypatch.setattr("cadmetrics.gui.jobs._inspect_model_with_options", fail_load)
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


def test_gui_csv_export_matches_result_schema(tmp_path: Path) -> None:
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

    lines = output.read_text(encoding="utf-8").splitlines()

    assert lines[0].split(",") == [spec.key for spec in RESULT_FIELD_SPECS]
    assert "model.stl" in lines[1]
    assert "stl-mesh-projection" in lines[1]
    assert lines[1].endswith(",note")


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
