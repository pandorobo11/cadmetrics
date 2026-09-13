from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6 import QtCore, QtWidgets

import cadmetrics.gui.pyside_app as pyside_app
from cadmetrics.gui.control_panel import ControlPanel
from cadmetrics.gui.gui_types import OperationState
from cadmetrics.gui.results_panel import ResultsPanel
from cadmetrics.gui.results_panel import DISPLAY_FIELDS
from cadmetrics.types import MeasurementRow, ModelData


class _FakeViewer(QtWidgets.QWidget):
    error = QtCore.Signal(str)
    message = QtCore.Signal(str)
    base_face_available = QtCore.Signal(bool)
    newly_exposed_surface_available = QtCore.Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.result_calls = []

    def set_options(self, options) -> None:
        pass

    def set_request(self, request) -> None:
        pass

    def set_model(self, model) -> None:
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

    request = panel.request()

    assert request.file == path
    assert request.attitude_mode == "roll_pitch"
    assert (request.roll_start, request.roll_end, request.roll_step) == (5.0, 15.0, 5.0)
    assert (request.pitch_start, request.pitch_end, request.pitch_step) == (2.0, 6.0, 2.0)
    assert panel.case_count.text() == "9 results"


def test_control_panel_busy_state_enables_cancel_only_while_calculating(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)

    panel.set_busy(OperationState.LOADING)

    assert panel.run_button.isEnabled() is False
    assert panel.file_edit.isEnabled() is False
    assert panel.cancel_button.isHidden() is True
    assert panel.cancel_button.isEnabled() is False

    panel.set_busy(OperationState.CALCULATING)
    assert panel.cancel_button.isHidden() is False
    assert panel.cancel_button.isEnabled() is True

    panel.set_busy(OperationState.CANCELLING)
    assert panel.cancel_button.isEnabled() is False


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


def test_advanced_changes_show_pending_state_only_after_model_load(qtbot, tmp_path: Path) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)
    panel.axis_x.setCurrentIndex(panel.axis_x.findData("-x"))

    assert panel.advanced_status.isHidden() is True
    assert panel.apply_advanced_button.isEnabled() is False

    path = tmp_path / "model.step"
    path.touch()
    panel.set_file_paths((path,))
    panel.set_model(_model(path, component_names=("Body",)))
    panel.axis_x.setCurrentIndex(panel.axis_x.findData("x"))

    assert panel.advanced_status.isHidden() is False
    assert panel.apply_advanced_button.isEnabled() is True


def test_control_panel_populates_step_components(qtbot, tmp_path: Path) -> None:
    path = tmp_path / "assembly.step"
    path.touch()
    panel = ControlPanel()
    qtbot.addWidget(panel)
    panel.set_file_paths((path,))
    panel.set_model(_model(path, component_names=("Body", "Left wing", "Right wing")))

    panel.component_none_button.click()
    assert all(not box.isChecked() for box in panel._component_checkboxes)
    panel.component_all_button.click()
    assert all(box.isChecked() for box in panel._component_checkboxes)
    panel._component_checkboxes[1].setChecked(False)
    panel.step_component_mode.setCurrentIndex(panel.step_component_mode.findData("subtract"))
    request = panel.request()

    assert request.step_components == (1, 3)
    assert request.step_component_mode == "subtract"
    assert panel.component_summary.text() == "2 of 3 components enabled."


def test_results_panel_displays_selects_and_exports_rows(qtbot, tmp_path: Path) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    rows = [
        replace(_row(), file="first.stl", alpha_deg=5.0, projected_area=1.25),
        replace(
            _row(),
            file="/models/aircraft/a-long-model-filename-that-needs-a-full-tooltip.stl",
            alpha_deg=15.0,
            projected_area=2.5,
        ),
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
    assert model.headerData(alpha_column, QtCore.Qt.Orientation.Horizontal) == "Alpha (°)"
    assert (
        model.headerData(
            area_column, QtCore.Qt.Orientation.Horizontal, QtCore.Qt.ItemDataRole.ToolTipRole
        )
        == "CSV field: projected_area"
    )
    assert model.data(model.index(0, alpha_column)) == "5"
    assert model.data(model.index(1, alpha_column)) == "15"
    assert model.data(model.index(1, area_column)) == "2.5"
    file_index = model.index(1, DISPLAY_FIELDS.index("file"))
    assert model.data(file_index) == rows[-1].file
    assert model.data(file_index, QtCore.Qt.ItemDataRole.ToolTipRole) == rows[-1].file

    output = tmp_path / "rows.csv"
    panel.save_csv(output)
    with output.open(encoding="utf-8", newline="") as stream:
        saved_rows = list(csv.DictReader(stream))
    assert [row["file"] for row in saved_rows] == [row.file for row in rows]
    assert [float(row["alpha_deg"]) for row in saved_rows] == [5.0, 15.0]


def test_main_window_invalidates_results_when_request_changes(
    qtbot, monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "model.step"
    source.touch()
    monkeypatch.setattr(pyside_app, "ModelViewer", _FakeViewer)
    window = pyside_app.MainWindow()
    qtbot.addWidget(window)
    window.controls.set_file_paths((source,))
    window._on_results_ready([_row()])
    assert window.results.rows
    assert window.results.save_button.isEnabled() is True

    window.controls.alpha_fields[0].setValue(10.0)

    assert window.results.rows == []
    assert window.results.save_button.isEnabled() is False
    assert window.viewer.result_calls[-1][0] is None
    assert window.progress_bar.value() == 0


@pytest.mark.parametrize(
    "change", ["input_unit", "output_unit", "existing_file", "missing_file", "empty_file"]
)
def test_main_window_invalidates_results_after_setup_edit(
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

    assert window.results.rows == []
    assert window.results.save_button.isEnabled() is False
    assert window.viewer.result_calls[-1][0] is None
    assert window.progress_bar.value() == 0
    with pytest.raises(ValueError, match="No calculation results to save"):
        window.results.save_csv(tmp_path / "stale.csv")


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


def _model(path: Path, *, component_names: tuple[str, ...]) -> ModelData:
    return ModelData(
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
        component_names=component_names,
        selected_components=tuple(range(1, len(component_names) + 1)),
    )


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
