from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("shapely")

from PySide6 import QtCore, QtWidgets  # noqa: E402

import cadmetrics.gui.pyside_app as pyside_app  # noqa: E402
from cadmetrics.api import inspect_model  # noqa: E402
from cadmetrics.gui.control_panel import ControlPanel  # noqa: E402
from cadmetrics.gui.gui_types import OperationState  # noqa: E402
from cadmetrics.gui.jobs import CalculationRequest  # noqa: E402
from cadmetrics.gui.sections_panel import SectionsPanel, section_chart_data  # noqa: E402
from cadmetrics.gui.viewer_geometry import section_plane_corners  # noqa: E402
from cadmetrics.sections import calculate_sections  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
CUBE = DATA_DIR / "unit_cube.stl"


class _FakeViewer(QtWidgets.QWidget):
    error = QtCore.Signal(str)
    message = QtCore.Signal(str)
    base_face_available = QtCore.Signal(bool)
    newly_exposed_surface_available = QtCore.Signal(bool)
    component_toggle_requested = QtCore.Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.result_calls = []
        self.sections = []
        self.section_mode = False

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
        self.result_calls.append(row)

    def set_section_mode(self, enabled: bool) -> None:
        self.section_mode = enabled

    def set_section(self, section) -> None:
        self.sections.append(section)

    def choose_and_save_image(self) -> None:
        pass


@pytest.fixture
def window(qtbot, monkeypatch):
    monkeypatch.setattr(pyside_app, "ModelViewer", _FakeViewer)
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *args: None)
    main_window = pyside_app.MainWindow()
    qtbot.addWidget(main_window)
    return main_window


def _cube_result(**kwargs):
    return calculate_sections(inspect_model(CUBE), section_count=11, **kwargs)


def test_sections_mode_swaps_the_attitude_inputs(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)
    panel.set_file_paths((CUBE,))
    changes = []
    panel.analysis_changed.connect(changes.append)

    panel.sections_mode_button.click()

    assert changes == ["sections"]
    assert panel.attitude_box.isHidden()
    assert not panel.sections_box.isHidden()
    assert panel.run_button.text() == "Run Sections"
    assert not panel.theta_count.isEnabled()
    assert panel.section_case_count.text() == "101 sections normal to X"

    panel.mach.setValue(1.5)
    panel.theta_count.setValue(8)
    panel.section_symmetric.setChecked(True)
    assert panel.theta_count.isEnabled()
    assert panel.section_case_count.text() == "5 roll angles × 101 sections"
    request = panel.request()
    assert request.analysis == "sections"
    assert (request.mach, request.theta_count, request.symmetric) == (1.5, 8, True)

    panel.theta_count.setValue(7)
    assert not panel.run_button.isEnabled()
    assert "even" in panel.validation_label.text()

    panel.projection_mode_button.click()
    assert panel.run_button.text() == "Run Sweep"
    assert panel.run_button.isEnabled()


def test_each_analysis_ignores_the_other_analysis_inputs() -> None:
    request = CalculationRequest(file=CUBE)

    assert replace(request, alpha_end=30.0).section_inputs() == request.section_inputs()
    assert replace(request, mach=2.0).projection_inputs() == request.projection_inputs()
    # Roll angles only matter above Mach 1.
    assert replace(request, theta_count=8).section_inputs() == request.section_inputs()
    supersonic = replace(request, mach=2.0)
    assert replace(supersonic, theta_count=8).section_inputs() != supersonic.section_inputs()


def test_sections_panel_shows_summary_chart_and_saves_csv(qtbot, tmp_path) -> None:
    panel = SectionsPanel()
    qtbot.addWidget(panel)
    panel.resize(900, 300)
    panel.show()
    selected = []
    panel.selected_row_changed.connect(selected.append)

    panel.set_result(_cube_result(), protected_paths=(CUBE,))
    panel.select_max_area()

    assert panel.stack.currentWidget() is panel.chart
    assert len(panel.chart.data.series) == 1
    assert "Max area 1 m²" in panel.summary_label.text()
    assert "blunt" in panel.warning_label.text()
    assert selected and selected[-1].area == pytest.approx(1.0)
    output = tmp_path / "sections.csv"
    panel.save_csv(output)
    rows = list(csv.DictReader(output.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 11
    with pytest.raises(ValueError, match="overwrite"):
        panel.save_csv(CUBE)


def test_supersonic_chart_has_one_line_per_roll_angle() -> None:
    result = _cube_result(mach=1.5, theta_count=4)
    data = section_chart_data(result.rows())

    assert data.series_label == "Theta"
    assert [series.value for series in data.series] == [-90.0, 0.0, 90.0, 180.0]


def test_section_plane_corners_lie_on_the_cutting_plane() -> None:
    vertices = np.array([[0.0, -1.0, -2.0], [3.0, 1.0, 2.0]])
    corners = section_plane_corners(vertices, (1.0, -0.5, 0.25), 1.0)

    assert corners @ np.array([1.0, -0.5, 0.25]) == pytest.approx(np.ones(4))
    assert corners[:, 1].min() < -1.0 and corners[:, 2].max() > 2.0


def test_main_window_runs_sections_without_touching_projection_results(window, qtbot) -> None:
    window.controls.set_file_paths((CUBE,))
    window.controls.sections_mode_button.click()
    assert window.results_stack.currentWidget() is window.sections
    assert window.viewer.section_mode
    assert window.run_action.text() == "Run Sections"

    window.controls.section_count.setValue(11)
    window.controls.run_button.click()
    qtbot.waitUntil(lambda: bool(window.sections.rows), timeout=10000)
    qtbot.waitUntil(lambda: window.controller.state is OperationState.IDLE)

    assert window.status.text() == "Done: 11 section(s)"
    assert window.results.rows == []
    assert window.save_csv_action.isEnabled()
    shown = [section for section in window.viewer.sections if section is not None]
    assert shown and shown[-1].loops
    assert shown[-1].overlay_lines[1].startswith("Section area  1 ")

    window.controls.mach.setValue(1.2)
    assert window.sections.is_stale
    window.controls.mach.setValue(1.0)
    assert not window.sections.is_stale

    window.controls.projection_mode_button.click()
    assert window.results_stack.currentWidget() is window.results
    assert not window.viewer.section_mode
    assert window.run_action.text() == "Run Sweep"
    assert not window.save_csv_action.isEnabled()
