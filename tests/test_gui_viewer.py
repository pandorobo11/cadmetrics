from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6 import QtWidgets

from cadmetrics.gui.gui_types import ViewerOptions
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
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.meshes = []
        self.arrows = []
        self.texts = []
        self.screenshots = []
        self.camera_position = None

    def render(self) -> None:
        pass

    def __getattr__(self, name):
        if name in {
            "set_background",
            "remove_all_lights",
            "add_light",
            "add_axes",
            "show_grid",
            "enable_parallel_projection",
            "clear",
            "render",
            "reset_camera",
            "reset_camera_clipping_range",
            "remove_actor",
            "enable_lightkit",
        }:
            return lambda *args, **kwargs: None
        raise AttributeError(name)

    def add_mesh(self, mesh, **kwargs):
        self.meshes.append((mesh, kwargs))
        return _Actor()

    def add_arrows(self, start, vector, **kwargs):
        self.arrows.append((start, vector, kwargs))
        return _Actor()

    def add_text(self, text, **kwargs):
        self.texts.append((text, kwargs))
        return _Actor()

    def screenshot(self, path: str) -> None:
        self.screenshots.append(path)


def test_model_viewer_renders_model_and_result(qtbot) -> None:
    plotter = None

    def factory(parent):
        nonlocal plotter
        plotter = _Plotter(parent)
        return plotter

    viewer = ModelViewer(plotter_factory=factory)
    qtbot.addWidget(viewer)
    viewer.set_request(CalculationRequest(file=Path("model.stl")))
    viewer.set_model(_model())
    view_text = plotter.texts[-1][0]
    viewer.set_result(_row(), CalculationRequest(file=Path("model.stl")), align_camera=True)
    result_text = plotter.texts[-1][0]

    assert viewer.available is True
    assert plotter is not None
    assert plotter.meshes
    assert any(options.get("color") == "#ff7a00" for _mesh, options in plotter.meshes)
    assert viewer._base_face_polydata is None
    assert plotter.arrows
    assert view_text.splitlines() == [
        "CADMETRICS",
        "model.stl",
        "STL  ·  m",
        "Surface area  6 m²",
        "Base area  0 m²",
        "Volume  1 m³",
    ]
    assert result_text.splitlines() == [
        *view_text.splitlines(),
        "Alpha 0°  ·  Beta 0°",
        "Projected area  1 m²",
    ]
    assert plotter.camera_position is not None


def test_model_viewer_applies_options_and_saves_image(qtbot, tmp_path: Path) -> None:
    plotter = None

    def factory(parent):
        nonlocal plotter
        plotter = _Plotter(parent)
        return plotter

    viewer = ModelViewer(plotter_factory=factory)
    qtbot.addWidget(viewer)
    viewer.set_model(_model())
    viewer.set_options(
        ViewerOptions(
            transparent_shape=True,
            feature_edges=False,
            show_projection_arrow=False,
            show_overlay=False,
        )
    )
    output = viewer.save_image(tmp_path / "view")

    assert output.suffix == ".png"
    assert plotter is not None
    assert plotter.screenshots == [str(output)]


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
        base_area=0.0,
        is_watertight=True,
        newly_exposed_surface_area=1.0,
        newly_exposed_face_indices=(6, 7),
    )


def _row() -> MeasurementRow:
    return MeasurementRow(
        file="model.stl",
        input_unit="m",
        output_unit="m",
        roll_deg=0.0,
        alpha_deg=0.0,
        beta_deg=0.0,
        direction_x=1.0,
        direction_y=0.0,
        direction_z=0.0,
        centroid_x=0.5,
        centroid_y=0.5,
        centroid_z=0.5,
        volume=1.0,
        surface_area=6.0,
        projected_area=1.0,
        is_watertight=True,
    )
