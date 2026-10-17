from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6 import QtWidgets

from cadmetrics.gui.gui_types import ViewerOptions
from cadmetrics.gui.jobs import CalculationRequest
from cadmetrics.gui.viewer import EMPTY_STATE_TEXT, OVERLAY_MARGIN, ModelViewer
from cadmetrics.gui.viewer_geometry import fit_overlay_text, overlay_reserved_fraction
from cadmetrics.types import MeasurementRow, ModelData


class _TextProperty:
    def __init__(self) -> None:
        self.calls: dict[str, tuple] = {}

    def __getattr__(self, name):
        return lambda *args: self.calls.__setitem__(name, args)


class _Actor:
    def __init__(self) -> None:
        self.prop = _TextProperty()
        self.visible = True

    def GetProperty(self):
        return self.prop

    def SetVisibility(self, visible) -> None:
        self.visible = bool(visible)


REFIT_GRID_BOUNDS = (-9.0, 9.0, -9.0, 9.0, -9.0, 9.0)


class _Camera:
    def __init__(self) -> None:
        self.parallel_scale = 1.0
        self.window_center = (0.0, 0.0)

    def zoom(self, factor) -> None:
        self.parallel_scale /= factor

    def SetWindowCenter(self, x, y) -> None:
        self.window_center = (x, y)


class _Plotter(QtWidgets.QWidget):
    """Record what the viewer asks VTK to draw without opening a render window."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.actors: dict[_Actor, tuple[str, object, dict]] = {}
        self.lights: list = []
        self.camera = _Camera()
        self.camera_position = None
        # Like PyVista, actor changes request a render unless render=False is passed.
        self.render_requests = 0

    def __getattr__(self, name):
        if name in {
            "set_background",
            "add_axes",
            "reset_camera",
            "reset_camera_clipping_range",
            "enable_parallel_projection",
            "remove_bounds_axes",
        }:
            return lambda *args, **kwargs: None
        raise AttributeError(name)

    def render(self) -> None:
        self.render_requests += 1

    def remove_all_lights(self) -> None:
        self.lights.clear()

    def add_light(self, light) -> None:
        self.lights.append(light)

    def clear(self) -> None:
        self.actors.clear()

    def _add(self, kind, data, kwargs):
        actor = _Actor()
        # PyVista refits the grid to every actor whenever actors change.
        for grid in self.active("grid"):
            grid.bounds = REFIT_GRID_BOUNDS
        self.actors[actor] = (kind, data, kwargs)
        if kwargs.get("render", True):
            self.render()
        return actor

    def show_grid(self, **kwargs):
        return self._add("grid", None, {**kwargs, "render": False})

    def add_mesh(self, mesh, **kwargs):
        return self._add("mesh", mesh, kwargs)

    def add_arrows(self, start, vector, **kwargs):
        return self._add("arrow", (start, vector), kwargs)

    def add_text(self, text, **kwargs):
        return self._add("text", text, kwargs)

    def remove_actor(self, actor, render=True) -> None:
        self.actors.pop(actor, None)
        if render:
            self.render()

    def active(self, kind):
        return {actor: entry for actor, entry in self.actors.items() if entry[0] == kind}


@pytest.fixture
def viewer(qtbot):
    plotters: list[_Plotter] = []

    def factory(parent):
        plotter = _Plotter(parent)
        plotters.append(plotter)
        return plotter

    widget = ModelViewer(plotter_factory=factory)
    widget.resize(900, 600)
    qtbot.addWidget(widget)
    return widget, plotters[0]


def test_invalid_request_without_result_shows_no_projection_arrow(viewer) -> None:
    widget, plotter = viewer
    widget.set_model(_model())
    widget.set_request(None)
    assert not plotter.active("arrow")

    widget.set_result(_row(), None)
    assert len(plotter.active("arrow")) == 1

    widget.set_result(None, None)
    assert not plotter.active("arrow")

    widget.set_request(CalculationRequest(file=Path("model.stl"), alpha_start=0.0))
    assert len(plotter.active("arrow")) == 1


def test_empty_state_hint_is_shown_until_a_model_loads(viewer) -> None:
    widget, plotter = viewer
    texts = [entry[1] for entry in plotter.active("text").values()]
    assert texts == [EMPTY_STATE_TEXT]
    assert "STL or STEP" in EMPTY_STATE_TEXT
    assert "drag and drop" in EMPTY_STATE_TEXT

    widget.resize(700, 500)
    assert [entry[1] for entry in plotter.active("text").values()] == [EMPTY_STATE_TEXT]

    widget.set_model(_model())
    texts = [entry[1] for entry in plotter.active("text").values()]
    assert EMPTY_STATE_TEXT not in texts
    assert widget._empty_state_actor is None


def test_overlay_has_background_panel_and_wraps_long_lines(viewer) -> None:
    widget, plotter = viewer
    widget.set_model(_model())
    widget.set_options(ViewerOptions(detailed_overlay=True))
    warning = "Mesh is not watertight; " * 12
    widget.set_result(replace(_row(), warnings=(warning,)), None)

    ((actor, (_, text, _)),) = plotter.active("text").items()
    lines = text.splitlines()
    assert any(line.strip().startswith("warnings:") for line in lines)
    assert lines[-1].rstrip().endswith("…")
    longest_allowed = max(len(line) for line in lines)
    assert longest_allowed < len(warning)
    calls = actor.prop.calls
    assert calls["SetBackgroundOpacity"][0] > 0.5
    assert calls["SetFrame"] == (True,)
    assert calls["SetVerticalJustification"] == (2,)


def test_overlay_reserves_space_and_shifts_scene_away_from_panel(viewer) -> None:
    widget, plotter = viewer
    widget.set_model(_model())
    reserve = widget._overlay_reserve
    assert 0.0 < reserve <= 0.45
    assert plotter.camera.window_center == pytest.approx((-reserve, 0.0))

    scale = plotter.camera.parallel_scale
    widget.set_options(ViewerOptions(show_overlay=False))
    assert widget._overlay_reserve == 0.0
    assert plotter.camera.window_center == (0.0, 0.0)
    # Releasing the reserved column enlarges the model by the same proportion.
    assert plotter.camera.parallel_scale == pytest.approx(scale * (1.0 - reserve))


def test_lights_follow_camera_and_markers_stay_bright(viewer) -> None:
    widget, plotter = viewer
    widget.set_model(_model())
    assert plotter.lights
    assert all(light.light_type in {1, 2} for light in plotter.lights)  # headlight, camera
    widget.set_result(_row(), CalculationRequest(file=Path("model.stl")), align_camera=True)

    centroid = [
        kwargs
        for _, mesh, kwargs in plotter.active("mesh").values()
        if np.allclose(mesh.center, (0.25, 0.2, 0.75))
    ]
    assert len(centroid) == 1
    assert centroid[0]["color"] == "#ffd400"
    assert centroid[0]["ambient"] >= 0.5
    ((_, _, arrow_kwargs),) = plotter.active("arrow").values()
    assert arrow_kwargs["ambient"] >= 0.4


def test_text_sizes_track_device_pixel_ratio(viewer, monkeypatch) -> None:
    widget, plotter = viewer
    monkeypatch.setattr(widget, "_device_pixel_ratio", lambda: 2.0)

    class _RenderWindow:
        def __init__(self, dpi) -> None:
            self.dpi = dpi

        def GetDPI(self):
            return self.dpi

    # VTK already scales text actors by the render-window DPI.
    plotter.ren_win = _RenderWindow(144)
    assert widget._text_font_size(12) == 12
    plotter.ren_win = _RenderWindow(72)
    assert widget._text_font_size(12) == 24

    widget.set_model(_model())
    ((_, _, grid_kwargs),) = plotter.active("grid").values()
    assert grid_kwargs["font_size"] == 24


def test_fit_overlay_text_wraps_and_elides() -> None:
    assert fit_overlay_text("short\nlines", 20) == "short\nlines"
    wrapped = fit_overlay_text("warnings: " + "word " * 10, 20).splitlines()
    assert len(wrapped) == 3
    assert all(len(line) <= 20 for line in wrapped)
    assert wrapped[1].startswith("  ")
    long = fit_overlay_text("warnings: " + "word " * 40, 20).splitlines()
    assert len(long) == 3
    assert long[-1].endswith("…")
    assert all(len(line) <= 20 for line in long)


def test_overlay_reserved_fraction_is_bounded() -> None:
    assert overlay_reserved_fraction(0.0, 800.0, limit=0.4) == 0.0
    assert overlay_reserved_fraction(200.0, 800.0, limit=0.4) == pytest.approx(0.25)
    assert overlay_reserved_fraction(700.0, 800.0, limit=0.4) == pytest.approx(0.4)
    assert overlay_reserved_fraction(100.0, 0.0, limit=0.4) == 0.0


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


def test_overlay_is_anchored_to_render_area_below_toolbar(viewer) -> None:
    widget, plotter = viewer
    widget.show()
    widget.set_model(_model())
    assert plotter.height() < widget.height()  # The view toolbar sits above the render area.

    ((_, (_, _, kwargs)),) = plotter.active("text").items()
    ratio = widget._device_pixel_ratio()
    _, top = kwargs["position"]
    assert top == pytest.approx(plotter.height() * ratio - OVERLAY_MARGIN * ratio)


def _component_model(selected: tuple[int, ...], mode: str = "filter") -> ModelData:
    base = _model()
    cube = (base.vertices, base.faces)
    shifted = (base.vertices + np.array([2.0, 0.0, 0.0]), base.faces)
    return replace(
        base,
        component_names=("A", "B"),
        selected_components=selected,
        step_component_mode=mode,
        component_meshes=(cube, shifted),
    )


def _meshes(plotter, widget=None) -> list[tuple[object, dict]]:
    """Model surfaces only: feature edges are drawn as a separate line mesh."""
    edges = None if widget is None else widget._feature_edges_actor
    return [
        (actor, entry[2]) for actor, entry in plotter.active("mesh").items() if actor is not edges
    ]


def test_unapplied_component_changes_preview_per_component(viewer) -> None:
    widget, plotter = viewer
    model = _component_model((1, 2))
    widget.set_model(model)
    widget.set_component_selection(((1, 2), "filter"))
    union = widget._mesh_actor
    assert widget.component_preview_active is False
    assert union.visible is True
    assert len(_meshes(plotter, widget)) == 1

    widget.set_component_selection(((1,), "filter"))
    assert widget.component_preview_active is True
    assert union.visible is False
    assert widget._feature_edges_actor.visible is False
    previews = [kwargs for actor, kwargs in _meshes(plotter, widget) if actor is not union]
    assert [kwargs["color"] for kwargs in previews] == ["#9fc8ef", "#9aa5b1"]
    assert previews[1]["opacity"] < 0.5
    texts = [entry[1] for entry in plotter.active("text").values()]
    assert any("Component preview" in text for text in texts)

    widget.set_component_selection(((1,), "subtract"))
    previews = [kwargs for actor, kwargs in _meshes(plotter, widget) if actor is not union]
    assert previews[1]["color"] == "#e0735f"

    # Back to the loaded selection: the union returns and preview actors are removed.
    widget.set_component_selection(((1, 2), "subtract"))
    assert widget.component_preview_active is False
    assert union.visible is True
    assert len(_meshes(plotter, widget)) == 1
    assert not any("Component preview" in entry[1] for entry in plotter.active("text").values())


def test_loading_a_model_with_the_new_selection_ends_the_preview(viewer) -> None:
    widget, plotter = viewer
    widget.set_model(_component_model((1, 2)))
    widget.set_component_selection(((2,), "filter"))
    assert widget.component_preview_active is True

    widget.set_model(_component_model((2,)))
    assert widget.component_preview_active is False
    assert len(_meshes(plotter, widget)) == 1
    assert widget._mesh_actor.visible is True


def test_mode_change_alone_previews_only_when_a_component_is_unchecked(viewer) -> None:
    widget, _ = viewer
    widget.set_model(_component_model((1, 2), mode="filter"))
    widget.set_component_selection(((1, 2), "subtract"))
    assert widget.component_preview_active is False

    widget.set_model(_component_model((1,), mode="filter"))
    widget.set_component_selection(((1,), "subtract"))
    assert widget.component_preview_active is True


def test_models_without_component_meshes_never_preview(viewer) -> None:
    widget, _ = viewer
    widget.set_model(_model())
    widget.set_component_selection(((1,), "filter"))
    assert widget.component_preview_active is False


def test_component_preview_keeps_the_grid_on_the_shown_geometry(viewer) -> None:
    widget, _ = viewer
    widget.set_model(_component_model((1,)))
    # Component 2 (x 2..3) is not in the loaded model; re-checking it widens the grid.
    widget.set_component_selection(((1, 2), "filter"))
    assert widget.component_preview_active is True
    assert tuple(widget._grid_actor.bounds) == (0.0, 3.0, 0.0, 1.0, 0.0, 1.0)

    widget.set_component_selection(((1,), "filter"))
    assert tuple(widget._grid_actor.bounds) == (0.0, 1.0, 0.0, 1.0, 0.0, 1.0)


def _many_component_model(count: int, selected: tuple[int, ...]) -> ModelData:
    base = _model()
    meshes = tuple(
        (base.vertices + np.array([2.0 * index, 0.0, 0.0]), base.faces) for index in range(count)
    )
    return replace(
        base,
        component_names=tuple(f"C{index}" for index in range(1, count + 1)),
        selected_components=selected,
        component_meshes=meshes,
    )


def test_component_preview_updates_render_once_regardless_of_component_count(viewer) -> None:
    widget, plotter = viewer
    count = 40
    widget.set_model(_many_component_model(count, tuple(range(1, count + 1))))

    plotter.render_requests = 0
    widget.set_component_selection((tuple(range(2, count + 1)), "filter"))
    assert widget.component_preview_active is True
    assert len(_meshes(plotter, widget)) == count + 1  # Hidden union plus every component.
    assert plotter.render_requests == 1

    plotter.render_requests = 0
    widget.set_component_selection((tuple(range(3, count + 1)), "subtract"))
    assert plotter.render_requests == 1

    plotter.render_requests = 0
    widget._update_component_preview(render=False)
    assert plotter.render_requests == 0

    # Back to the loaded selection: removing every preview actor still renders once.
    plotter.render_requests = 0
    widget.set_component_selection((tuple(range(1, count + 1)), "subtract"))
    assert widget.component_preview_active is False
    assert plotter.render_requests == 1


def test_resizing_during_a_component_preview_only_moves_the_notice(viewer, qtbot) -> None:
    widget, plotter = viewer
    count = 40
    widget.show()
    widget.set_model(_many_component_model(count, tuple(range(1, count + 1))))

    def resize_render_requests(width: int) -> int:
        plotter.render_requests = 0
        widget.resize(width, 500)
        qtbot.waitUntil(lambda: plotter.render_requests > 0)
        return plotter.render_requests

    without_preview = resize_render_requests(800)
    widget.set_component_selection((tuple(range(2, count + 1)), "filter"))
    previews = set(widget._component_preview_actors)

    # The preview adds no render requests per component, and its actors are kept.
    assert resize_render_requests(700) == without_preview
    assert set(widget._component_preview_actors) == previews
    texts = [entry[1] for entry in plotter.active("text").values()]
    assert sum("Component preview" in text for text in texts) == 1


def test_projection_updates_keep_the_grid_on_the_component_preview(viewer) -> None:
    widget, plotter = viewer
    widget.set_model(_component_model((1,)))
    widget.set_component_selection(((1, 2), "filter"))
    preview_bounds = (0.0, 3.0, 0.0, 1.0, 0.0, 1.0)
    assert tuple(widget._grid_actor.bounds) == preview_bounds

    widget.set_request(CalculationRequest(file=Path("model.stl"), alpha_start=0.0))
    assert len(plotter.active("arrow")) == 1  # The arrow refits the grid in PyVista.
    assert tuple(widget._grid_actor.bounds) == preview_bounds

    widget.set_result(_row(), None)
    assert tuple(widget._grid_actor.bounds) == preview_bounds

    widget.set_component_selection(((1,), "filter"))
    assert tuple(widget._grid_actor.bounds) == (0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
    widget.set_request(CalculationRequest(file=Path("model.stl"), alpha_start=5.0))
    assert tuple(widget._grid_actor.bounds) == (0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
