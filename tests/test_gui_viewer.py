from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6 import QtWidgets

import cadmetrics.gui.pyside_app as pyside_app
from cadmetrics.gui.jobs import CalculationRequest
from cadmetrics.gui.viewer import ModelViewer
from cadmetrics.types import MeasurementRow, ModelData


class _Property:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class _Actor:
    prop = _Property()

    def GetProperty(self):
        return self.prop


class _Plotter(QtWidgets.QWidget):
    """Observe renderer requests and actor lifetimes without starting a VTK window."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.actors = {}
        self.screenshots = []
        self.camera_position = None
        self.parallel_projection = False

    def __getattr__(self, name):
        if name in {
            "set_background",
            "remove_all_lights",
            "add_light",
            "add_axes",
            "show_grid",
            "render",
            "reset_camera",
            "reset_camera_clipping_range",
            "enable_lightkit",
        }:
            return lambda *args, **kwargs: None
        raise AttributeError(name)

    def clear(self) -> None:
        self.actors.clear()

    def render(self) -> None:
        pass

    def enable_parallel_projection(self) -> None:
        self.parallel_projection = True

    def _add(self, kind, data):
        actor = _Actor()
        self.actors[actor] = (kind, data)
        return actor

    def add_mesh(self, mesh, **kwargs):
        return self._add("mesh", mesh)

    def add_arrows(self, start, vector, **kwargs):
        return self._add("arrow", (start, vector))

    def add_text(self, text, **kwargs):
        return self._add("text", text)

    def remove_actor(self, actor) -> None:
        del self.actors[actor]

    def screenshot(self, path: str) -> None:
        self.screenshots.append(path)

    def active(self, kind):
        return {
            actor: data for actor, (actor_kind, data) in self.actors.items() if actor_kind == kind
        }


@pytest.fixture
def viewer_window(qtbot, monkeypatch):
    plotters = []

    def factory(parent):
        plotter = _Plotter(parent)
        plotters.append(plotter)
        return plotter

    monkeypatch.setattr(
        pyside_app, "ModelViewer", lambda parent: ModelViewer(parent, plotter_factory=factory)
    )
    window = pyside_app.MainWindow()
    qtbot.addWidget(window)
    return window, plotters[0]


def test_model_viewer_renders_model_and_result(viewer_window) -> None:
    window, plotter = viewer_window
    viewer = window.viewer
    request = CalculationRequest(file=Path("model.stl"))
    model = _model()
    viewer.set_request(request)
    viewer.set_model(model)

    view_text = next(iter(plotter.active("text").values()))
    assert "model.stl" in view_text
    assert "Surface area  6 m²" in view_text
    assert "Base area  1 m²" in view_text
    assert "Volume  1 m³" in view_text
    assert window.controls.show_base_face.isEnabled()
    assert window.controls.show_newly_exposed_surface.isEnabled()

    meshes = plotter.active("mesh")
    exposed_actors = [
        actor for actor, mesh in meshes.items() if np.allclose(mesh.points[:, 2], 0.0, atol=1.0e-3)
    ]
    assert len(exposed_actors) == 1
    window.controls.show_newly_exposed_surface.setChecked(False)
    assert exposed_actors[0] not in plotter.actors
    assert not any(
        np.allclose(mesh.points[:, 2], 0.0, atol=1.0e-3) for mesh in plotter.active("mesh").values()
    )
    window.controls.show_newly_exposed_surface.setChecked(True)

    meshes = plotter.active("mesh")
    window.controls.show_base_face.setChecked(True)
    added = plotter.active("mesh").keys() - meshes.keys()
    base_actors = [
        actor
        for actor in added
        if np.allclose(plotter.active("mesh")[actor].points[:, 0], 1.0, atol=1.0e-3)
    ]
    assert len(base_actors) == 1
    window.controls.show_base_face.setChecked(False)
    assert base_actors[0] not in plotter.actors

    viewer.set_result(_row(), request, align_camera=True)
    centroid = (0.25, 0.2, 0.75)
    assert any(np.allclose(mesh.center, centroid) for mesh in plotter.active("mesh").values())
    result_text = next(iter(plotter.active("text").values()))
    assert "Alpha 12°" in result_text and "Beta 3°" in result_text
    assert "Projected area  0.8 m²" in result_text

    viewer.set_camera((0.0, 0.0, 1.0))
    position, focal_point, _ = plotter.camera_position
    offset = np.asarray(position) - np.asarray(focal_point)
    assert offset / np.linalg.norm(offset) == pytest.approx((0.0, 0.0, 1.0))
    assert plotter.parallel_projection

    assert plotter.active("arrow")
    window.controls.show_projection_arrow.setChecked(False)
    assert not plotter.active("arrow")
    window.controls.show_centroid.setChecked(False)
    assert not any(np.allclose(mesh.center, centroid) for mesh in plotter.active("mesh").values())
    window.controls.show_centroid.setChecked(True)
    assert any(np.allclose(mesh.center, centroid) for mesh in plotter.active("mesh").values())

    window.controls.show_base_face.setChecked(True)
    viewer.set_model(replace(model, base_area=0.0, newly_exposed_face_indices=(6, 7)))
    assert not window.controls.show_base_face.isEnabled()
    assert not window.controls.show_base_face.isChecked()


def test_gui_view_can_be_saved_as_image(viewer_window, tmp_path: Path) -> None:
    window, plotter = viewer_window

    output = window.viewer.save_image(tmp_path / "view")

    assert output == tmp_path / "view.png"
    assert plotter.screenshots == [str(output)]


def test_gui_documentation_action_builds_then_reuses_local_site(
    viewer_window, monkeypatch, tmp_path: Path
) -> None:
    window, _ = viewer_window
    project = tmp_path / "project"
    source_file = project / "src" / "cadmetrics" / "gui" / "pyside_app.py"
    source_file.parent.mkdir(parents=True)
    source_file.touch()
    (project / "docs").mkdir()
    (project / "README.md").write_text("# Initial documentation\n", encoding="utf-8")
    (project / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (project / "mkdocs.yml").write_text("site_name: GUI docs test\n", encoding="utf-8")
    monkeypatch.setattr(pyside_app, "__file__", str(source_file))
    opened = []
    monkeypatch.setattr(
        pyside_app.QtGui.QDesktopServices, "openUrl", lambda url: opened.append(url) or True
    )
    menu_bar = window.menuBar()
    help_action = next(action for action in menu_bar.actions() if action.text() == "Help")
    help_menu = help_action.menu()
    documentation = next(
        action for action in help_menu.actions() if action.text() == "Documentation"
    )

    documentation.trigger()

    assert len(opened) == 1
    index = Path(opened[0].toLocalFile())
    assert "Initial documentation" in index.read_text(encoding="utf-8")
    (project / "README.md").write_text("# Changed documentation\n", encoding="utf-8")

    documentation.trigger()

    assert [Path(url.toLocalFile()) for url in opened] == [index, index]
    assert "Changed documentation" not in index.read_text(encoding="utf-8")


def test_control_panel_errors_reach_main_window_handler(viewer_window, monkeypatch) -> None:
    window, _ = viewer_window
    errors = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox, "critical", lambda parent, title, message: errors.append(message)
    )

    window.controls.run_button.click()

    assert len(errors) == 1
    assert "file" in errors[0].lower()
    assert errors[0] in window.status.text()


def _model() -> ModelData:
    vertices = np.array(
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
    )
    faces = np.array(
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
    )
    return ModelData(
        path=Path("model.stl"),
        source_format="stl",
        vertices=vertices,
        faces=faces,
        input_unit="m",
        output_unit="m",
        volume=1.0,
        surface_area=6.0,
        base_area=1.0,
        is_watertight=True,
        newly_exposed_surface_area=1.0,
        newly_exposed_face_indices=(0, 1),
    )


def _row() -> MeasurementRow:
    return MeasurementRow(
        file="model.stl",
        input_unit="m",
        output_unit="m",
        roll_deg=0.0,
        alpha_deg=12.0,
        beta_deg=3.0,
        direction_x=1.0,
        direction_y=0.0,
        direction_z=0.0,
        centroid_x=0.25,
        centroid_y=0.2,
        centroid_z=0.75,
        volume=1.0,
        surface_area=6.0,
        projected_area=0.8,
        is_watertight=True,
    )
