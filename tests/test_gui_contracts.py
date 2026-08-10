from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cadmetrics.gui.gui_formatters import (
    component_display_groups,
    format_file_selection,
    format_model_file_label,
    overlay_text,
)
from cadmetrics.gui.gui_types import ModelLoadKey, OperationState, ViewerOptions
from cadmetrics.gui.jobs import CalculationRequest
from cadmetrics.types import MeasurementRow


def test_model_load_key_only_tracks_geometry_loading_options() -> None:
    request = CalculationRequest(file=Path("model.step"), alpha_start=1.0)
    changed_attitude = replace(request, alpha_start=25.0, beta_end=10.0)
    changed_geometry = replace(request, axis_map="-x,y,z")
    changed_component_mode = replace(request, step_component_mode="subtract")

    assert ModelLoadKey.from_request(request) == ModelLoadKey.from_request(changed_attitude)
    assert ModelLoadKey.from_request(request) != ModelLoadKey.from_request(changed_geometry)
    assert ModelLoadKey.from_request(request) != ModelLoadKey.from_request(changed_component_mode)


def test_viewer_options_and_operation_states_have_stable_defaults() -> None:
    options = ViewerOptions()

    assert options.feature_edges is True
    assert options.show_projection_arrow is True
    assert options.show_centroid is True
    assert options.show_newly_exposed_surface is True
    assert options.camera_direction == (-1.0, -1.0, 1.0)
    assert [state.value for state in OperationState] == [
        "idle",
        "loading",
        "calculating",
        "cancelling",
    ]


def test_gui_file_and_component_formatters() -> None:
    paths = (Path("/tmp/body.step"), Path("/tmp/wing.step"), Path("/tmp/tail.step"))

    assert format_file_selection(paths) == "body.step + 2 more"
    assert format_model_file_label(Path("; ".join(str(path) for path in paths))) == (
        "body.step + wing.step + tail.step"
    )
    assert component_display_groups(
        ("body.step: Body", "body.step: Fairing", "wing.step: Wing"), grouped=True
    ) == [
        ("body.step", [(1, "Body"), (2, "Fairing")]),
        ("wing.step", [(3, "Wing")]),
    ]


def test_overlay_formatter_preserves_result_summary() -> None:
    row = MeasurementRow(
        file="model.stl",
        input_unit="m",
        output_unit="m",
        roll_deg=0.0,
        alpha_deg=0.0,
        beta_deg=0.0,
        volume=1.0,
        surface_area=6.0,
        base_area=1.0,
        projected_area=1.0,
        is_watertight=True,
    )

    text = overlay_text(row, model=None, request=None)

    assert text.startswith("CADMETRICS\nmodel.stl")
    assert "Surface area  6 m²" in text
    assert "Base area  1 m²" in text
    assert "Projected area  1 m²" in text
    assert "Volume  1 m³" in text
    assert "surface_area" not in text


def test_control_panel_errors_reach_main_window_handler(qtbot, monkeypatch) -> None:
    QtCore = pytest.importorskip("PySide6.QtCore")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    import cadmetrics.gui.pyside_app as pyside_app

    class FakeViewer(QtWidgets.QWidget):
        error = QtCore.Signal(str)
        message = QtCore.Signal(str)
        base_face_available = QtCore.Signal(bool)
        newly_exposed_surface_available = QtCore.Signal(bool)

        def set_options(self, options) -> None:
            pass

        def set_request(self, request) -> None:
            pass

        def set_model(self, model) -> None:
            pass

        def set_result(self, row, request, *, align_camera=False) -> None:
            pass

        def choose_and_save_image(self) -> None:
            pass

    errors = []
    monkeypatch.setattr(pyside_app, "ModelViewer", FakeViewer)
    monkeypatch.setattr(
        pyside_app.MainWindow,
        "_show_error",
        lambda self, message: errors.append(message),
    )
    window = pyside_app.MainWindow()
    qtbot.addWidget(window)

    window.controls.run_button.click()

    assert len(errors) == 1
    assert "file" in errors[0].lower()
