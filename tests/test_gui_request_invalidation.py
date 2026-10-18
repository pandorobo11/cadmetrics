from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6 import QtCore, QtWidgets

import cadmetrics.gui.pyside_app as pyside_app
from cadmetrics.gui.gui_types import OperationState
from cadmetrics.types import MeasurementRow, ModelData


class _Viewer(QtWidgets.QWidget):
    error = QtCore.Signal(str)
    message = QtCore.Signal(str)
    base_face_available = QtCore.Signal(bool)
    newly_exposed_surface_available = QtCore.Signal(bool)
    component_toggle_requested = QtCore.Signal(int)

    def set_options(self, options) -> None:
        pass

    def set_request(self, request) -> None:
        pass

    def set_model(self, model) -> None:
        pass

    def set_component_selection(self, selection) -> None:
        pass

    def set_highlighted_component(self, index) -> None:
        pass

    def set_result(self, row, request, *, align_camera=False) -> None:
        pass

    def choose_and_save_image(self) -> None:
        pass


@pytest.fixture
def window(qtbot, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pyside_app, "ModelViewer", _Viewer)
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *args: None)
    window = pyside_app.MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "assembly.step"
    path.touch()
    window.controls.set_file_paths((path,))
    window.controls.mesh_deflection_auto.setChecked(False)
    window._on_model_loaded(
        ModelData(
            path=path,
            source_format="step",
            vertices=np.empty((0, 3), dtype=float),
            faces=np.empty((0, 3), dtype=np.int64),
            input_unit="m",
            output_unit="m",
            volume=1.0,
            surface_area=6.0,
            base_area=1.0,
            is_watertight=True,
            component_names=("Body", "Cutter"),
            selected_components=(1, 2),
        )
    )
    window._request = window._results_request = window.controls.request()
    window._on_results_ready(
        [
            MeasurementRow(
                file=str(path),
                input_unit="m",
                output_unit="m",
                roll_deg=0.0,
                alpha_deg=0.0,
                beta_deg=0.0,
                volume=1.0,
                surface_area=6.0,
                projected_area=1.0,
                is_watertight=True,
            )
        ]
    )
    return window


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("axis_x", "-x"),
        ("axis_y", "-y"),
        ("axis_z", "-z"),
        ("step_component_mode", "subtract"),
        ("step_metrics", "mesh"),
        ("mesh_deflection", 0.002),
        ("angular_deflection", 0.2),
        ("base_tolerance", 0.01),
        ("mesh_deflection_auto", True),
    ],
)
def test_advanced_edit_marks_results_stale_and_reverting_restores_them(window, name, value):
    original = window._results_request
    rows = window.results.rows
    field = getattr(window.controls, name)
    if isinstance(field, QtWidgets.QComboBox):
        previous = field.currentIndex()
        value = field.findData(value)
        set_value = field.setCurrentIndex
    elif isinstance(field, QtWidgets.QCheckBox):
        previous = field.isChecked()
        set_value = field.setChecked
    else:
        previous = field.value()
        set_value = field.setValue

    set_value(value)

    assert window._request == window.controls.request()
    assert window._request != original
    assert window._results_request == original
    assert window.results.rows == rows
    assert window.results.is_stale
    assert window.results.can_save
    assert "out of date" in window.status.text()

    set_value(previous)

    assert window._request == original
    assert not window.results.is_stale
    assert window.results.rows == rows


def test_component_changes_including_empty_selection_mark_results_stale(window):
    original = window._results_request
    first, second = window.controls._component_checkboxes
    second.setChecked(False)
    assert window.results.is_stale
    assert window._request.step_components == (1,)
    assert window._results_request == original

    first.setChecked(False)
    assert window._request is None
    assert window.results.is_stale
    assert window.results.can_save

    first.setChecked(True)
    second.setChecked(True)
    assert window._request == original
    assert not window.results.is_stale


@pytest.mark.parametrize("terminal", ["success", "cancel", "failure"])
def test_edit_during_calculation_marks_retained_rows_stale_at_every_terminal(window, terminal):
    original = window._results_request
    rows = window.results.rows
    window._calculation_running = True
    window._on_state_changed(OperationState.CALCULATING)
    window.controls.base_tolerance.setValue(0.01)
    assert not window.results.is_stale

    if terminal == "success":
        window._on_results_ready(rows)
    elif terminal == "cancel":
        window._on_cancelled()
    else:
        window._on_failed("projection failed")
    window._on_state_changed(OperationState.IDLE)

    assert window._request != original
    assert window._results_request == original
    assert window.results.rows == rows
    assert window.results.is_stale
    assert window.results.can_save
    if terminal == "failure":
        assert window.status.text() == "Error: projection failed"


def test_display_only_changes_do_not_mark_results_stale(window):
    original = window._results_request
    window.controls.show_overlay.setChecked(False)
    assert window._request == original
    assert not window.results.is_stale
