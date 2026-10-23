from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6 import QtCore, QtWidgets

import cadmetrics.gui.pyside_app as pyside_app
import cadmetrics.gui.results_panel as results_panel
from cadmetrics.gui.control_panel import ControlPanel
from cadmetrics.gui.results_panel import ResultsPanel
from cadmetrics.gui.results_panel import DISPLAY_FIELDS
from cadmetrics.types import MeasurementRow


class _FakeViewer(QtWidgets.QWidget):
    error = QtCore.Signal(str)
    message = QtCore.Signal(str)
    base_face_available = QtCore.Signal(bool)
    newly_exposed_surface_available = QtCore.Signal(bool)
    component_toggle_requested = QtCore.Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.result_calls = []

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
        self.result_calls.append((row, request, align_camera))

    def choose_and_save_image(self) -> None:
        pass


def test_control_panel_builds_roll_pitch_request_and_counts_cases(qtbot, tmp_path: Path) -> None:
    path = tmp_path / "model.step"
    path.touch()
    panel = ControlPanel()
    qtbot.addWidget(panel)
    panel.set_file_paths((path,))
    panel.attitude_mode.setCurrentIndex(panel.attitude_mode.findData("roll_pitch"))
    for field, value in zip(panel.roll_fields, (5.0, 15.0, 5.0), strict=True):
        field.setValue(value)
    for field, value in zip(panel.pitch_fields, (2.0, 6.0, 2.0), strict=True):
        field.setValue(value)
    panel.axis_y.setCurrentIndex(panel.axis_y.findData("-y"))
    panel.axis_z.setCurrentIndex(panel.axis_z.findData("-z"))

    request = panel.request()

    assert request.file == path
    assert request.attitude_mode == "roll_pitch"
    assert (request.roll_start, request.roll_end, request.roll_step) == (5.0, 15.0, 5.0)
    assert (request.pitch_start, request.pitch_end, request.pitch_step) == (2.0, 6.0, 2.0)
    assert request.axis_map == "x,-y,-z"
    assert panel.case_count.text() == "9 results"


def test_collapsible_section_shows_and_hides_contents(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)
    toggle = panel._section_toggles["Model Details"]
    content = toggle.parentWidget().findChild(QtWidgets.QGroupBox, "sectionContent")

    assert content is not None
    assert not content.isVisibleTo(panel)
    toggle.click()
    assert content.isVisibleTo(panel)
    toggle.click()
    assert not content.isVisibleTo(panel)


def test_run_button_is_outside_scrolling_settings(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)

    assert panel.scroll_area.isAncestorOf(panel.run_button) is False


def test_detailed_overlay_option_is_opt_in(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)

    assert panel.viewer_options().show_centroid is True
    assert panel.viewer_options().detailed_overlay is False
    panel.show_centroid.setChecked(False)
    panel.detailed_overlay.setChecked(True)
    assert panel.viewer_options().show_centroid is False
    assert panel.viewer_options().detailed_overlay is True


def test_results_panel_displays_and_selects_rows(qtbot) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    rows = [
        replace(_row(), alpha_deg=5.0, projected_area=1.25),
        replace(_row(), alpha_deg=15.0, projected_area=2.5),
    ]
    selected = []
    panel.selected_row_changed.connect(selected.append)
    assert panel.stack.currentWidget() is panel.empty_state

    panel.set_rows(rows)
    panel.select_last_row()

    assert panel.stack.currentWidget() is panel.table
    assert panel.result_count.text() == "Rows: 2"
    assert selected == [rows[-1]]
    model = panel.table.model()
    assert model.rowCount() == 2
    alpha_column = DISPLAY_FIELDS.index("alpha_deg")
    area_column = DISPLAY_FIELDS.index("projected_area")
    assert (
        model.headerData(
            area_column, QtCore.Qt.Orientation.Horizontal, QtCore.Qt.ItemDataRole.ToolTipRole
        )
        == "CSV field: projected_area"
    )
    assert model.data(model.index(0, alpha_column)) == "5"
    assert model.data(model.index(1, alpha_column)) == "15"
    assert model.data(model.index(1, area_column)) == "2.5"


@pytest.mark.parametrize(
    "change", ["input_unit", "output_unit", "existing_file", "missing_file", "empty_file"]
)
def test_main_window_marks_results_stale_after_setup_edit(
    qtbot, monkeypatch, tmp_path: Path, change: str
) -> None:
    source = tmp_path / "model.stl"
    source.touch()
    other = tmp_path / "other.stl"
    other.touch()
    monkeypatch.setattr(pyside_app, "ModelViewer", _FakeViewer)
    window = pyside_app.MainWindow()
    qtbot.addWidget(window)
    window.controls.set_file_paths((source,))
    window._request = window.controls.request()
    window._on_results_ready([_row()])

    if change == "input_unit":
        window.controls.input_unit.setCurrentText("mm")
    elif change == "output_unit":
        window.controls.output_unit.setCurrentText("mm")
    elif change == "existing_file":
        window.controls.file_edit.setText(str(other))
    elif change == "missing_file":
        window.controls.file_edit.setText(str(tmp_path / "missing.stl"))
    else:
        window.controls.file_edit.clear()

    assert window.results.rows
    assert window.results.is_stale
    assert window.results.save_button.isEnabled() is True
    assert window.viewer.result_calls[-1][0] is None


def test_main_window_setup_edits_are_applied_by_next_sweep(
    qtbot, monkeypatch, tmp_path: Path
) -> None:
    paths = (tmp_path / "body.stl", tmp_path / "wing.stl")
    for path in paths:
        path.touch()
    monkeypatch.setattr(pyside_app, "ModelViewer", _FakeViewer)
    window = pyside_app.MainWindow()
    qtbot.addWidget(window)
    loads = []
    calculations = []
    monkeypatch.setattr(window.controller, "load_only", loads.append)
    monkeypatch.setattr(window.controller, "calculate", calculations.append)

    window.controls.set_file_paths(paths)
    window.controls.input_unit.setCurrentText("mm")
    window.controls.output_unit.setCurrentText("cm")

    assert loads == calculations == []
    window.controls.run_button.click()

    assert loads == []
    assert len(calculations) == 1
    assert calculations[0].file == paths
    assert calculations[0].input_unit == "mm"
    assert calculations[0].output_unit == "cm"


def test_main_window_protects_request_files_from_csv_export(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from cadmetrics.gui.jobs import CalculationRequest

    source = tmp_path / "model.step"
    source.write_bytes(b"STEP source data")
    monkeypatch.setattr(pyside_app, "ModelViewer", _FakeViewer)
    window = pyside_app.MainWindow()
    qtbot.addWidget(window)
    window._request = CalculationRequest(file=source)

    window._on_results_ready([_row()])

    with pytest.raises(ValueError, match="must not overwrite an input CAD file"):
        window.results.save_csv(source)
    assert source.read_bytes() == b"STEP source data"


def _row() -> MeasurementRow:
    return MeasurementRow(
        file="model.stl",
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


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_result_selection_keeps_row_preview_with_cocoa_single_cell(qtbot, monkeypatch, platform):
    monkeypatch.setattr(results_panel.sys, "platform", platform)
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.resize(900, 250)
    panel.show()
    rows = [replace(_row(), file="first.stl"), replace(_row(), file="second.stl")]
    selected = []
    panel.selected_row_changed.connect(selected.append)
    panel.set_rows(rows)
    panel.select_last_row()
    panel.table.setFocus()
    qtbot.waitUntil(lambda: panel.table.hasFocus())

    expected = 1 if platform == "darwin" else len(DISPLAY_FIELDS)
    assert len(panel.table.selectionModel().selectedIndexes()) == expected
    assert selected[-1] is rows[1]
    qtbot.keyClick(panel.table, QtCore.Qt.Key.Key_Up)
    assert selected[-1] is rows[0]
    assert len(panel.table.selectionModel().selectedIndexes()) == expected

    if platform == "darwin":
        # Only the first cell is natively selected, but the visible full row must
        # still be highlighted. Compare blank areas in multiple actual painted cells.
        visible = [c for c in range(len(DISPLAY_FIELDS)) if not panel.table.isColumnHidden(c)][:3]
        assert not panel.table.selectionModel().isSelected(panel.table.model().index(0, visible[2]))
        image = panel.table.viewport().grab().toImage()
        colors = []
        for column in visible:
            rect = panel.table.visualRect(panel.table.model().index(0, column))
            colors.append(image.pixelColor(rect.right() - 8, rect.bottom() - 5))
        # The focused cell may have a distinct focus decoration; unselected
        # cells in the current row must share the highlight, not the background.
        assert colors[1] == colors[2]
        for column, color in zip(visible, colors, strict=True):
            rect = panel.table.visualRect(panel.table.model().index(1, column))
            assert color != image.pixelColor(rect.right() - 8, rect.bottom() - 5)

    panel.clear()
    assert not panel.table.selectionModel().hasSelection()
    panel.set_rows(rows)
    panel.select_last_row()
    assert selected[-1] is rows[1]
    assert len(panel.table.selectionModel().selectedIndexes()) == expected


def test_results_hide_the_file_column(qtbot) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    assert panel.table.isColumnHidden(DISPLAY_FIELDS.index("file")) is True
