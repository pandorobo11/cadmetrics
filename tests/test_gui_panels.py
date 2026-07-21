from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6 import QtCore, QtWidgets

import cadmetrics.gui.pyside_app as pyside_app
from cadmetrics.cli import CSV_FIELDS
from cadmetrics.gui.control_panel import ControlPanel
from cadmetrics.gui.gui_types import OperationState
from cadmetrics.gui.results_panel import ResultsPanel
from cadmetrics.gui.results_panel import DEFAULT_COLUMN_WIDTH
from cadmetrics.gui.results_panel import DISPLAY_FIELDS, RESULT_HEADER_LABELS
from cadmetrics.gui.styles import (
    application_stylesheet,
    disclosure_arrow_image_urls,
    spinbox_arrow_image_urls,
)
from cadmetrics.types import MeasurementRow, ModelData


class _FakeViewer(QtWidgets.QWidget):
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


def test_control_panel_builds_roll_pitch_request(qtbot, tmp_path: Path) -> None:
    path = tmp_path / "model.step"
    path.touch()
    panel = ControlPanel()
    qtbot.addWidget(panel)
    panel.set_file_paths((path,))
    panel.attitude_mode.setCurrentIndex(panel.attitude_mode.findData("roll_pitch"))
    panel.roll_fields[0].setValue(5.0)
    panel.roll_fields[1].setValue(10.0)
    panel.pitch_fields[0].setValue(2.0)

    request = panel.request()

    assert request.file == path
    assert request.attitude_mode == "roll_pitch"
    assert (request.roll_start, request.roll_end) == (5.0, 10.0)
    assert request.pitch_start == 2.0


def test_control_panel_busy_state_enables_only_cancel(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)

    panel.set_busy(OperationState.LOADING)

    assert panel.run_button.isEnabled() is False
    assert panel.file_edit.isEnabled() is False
    assert panel.cancel_button.isEnabled() is True

    panel.set_busy(OperationState.CANCELLING)
    assert panel.cancel_button.isEnabled() is False


def test_control_panel_emits_preview_request_for_attitude_change(qtbot, tmp_path: Path) -> None:
    path = tmp_path / "model.stl"
    path.touch()
    panel = ControlPanel()
    qtbot.addWidget(panel)
    panel.set_file_paths((path,))
    requests = []
    panel.request_changed.connect(requests.append)

    panel.alpha_fields[0].setValue(12.0)

    assert requests[-1].alpha_start == 12.0


def test_control_panel_restores_compact_form_layout(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)
    setup_form = panel.file_edit.parentWidget().layout()
    margins = setup_form.contentsMargins()

    assert setup_form.fieldGrowthPolicy() == (
        QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
    )
    assert setup_form.verticalSpacing() == 6
    assert setup_form.horizontalSpacing() == 10
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (8, 6, 8, 7)


def test_sweep_grid_keeps_columns_even_and_unclipped(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)
    grid = panel.alpha_beta_group.layout()
    margins = grid.contentsMargins()

    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (0, 0, 0, 0)
    assert grid.horizontalSpacing() == 6
    assert grid.verticalSpacing() == 3
    assert [grid.columnStretch(column) for column in (1, 2, 3)] == [1, 1, 1]
    assert all(field.minimumWidth() == 70 for field in panel.alpha_fields)


def test_collapsible_sections_and_model_details_stay_compact(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)
    toggle = panel._section_toggles["Model Details"]
    collapsed_icon = toggle.icon().cacheKey()
    section = toggle.parentWidget()
    content = section.findChild(QtWidgets.QGroupBox, "sectionContent")

    assert toggle.arrowType() == QtCore.Qt.ArrowType.NoArrow
    assert toggle.sizePolicy().horizontalPolicy() == QtWidgets.QSizePolicy.Policy.Expanding
    assert section.layout().spacing() == 3
    assert content is not None
    toggle.setChecked(True)
    assert toggle.icon().cacheKey() != collapsed_icon
    assert content.isVisibleTo(panel)
    assert panel.model_info.sizePolicy().verticalPolicy() == QtWidgets.QSizePolicy.Policy.Fixed


def test_application_stylesheet_restores_indicator_and_spinbox_rules() -> None:
    stylesheet = application_stylesheet()
    arrow_assets = [Path(path).read_text(encoding="utf-8") for path in spinbox_arrow_image_urls()]
    disclosure_assets = [
        Path(path).read_text(encoding="utf-8") for path in disclosure_arrow_image_urls()
    ]

    assert "QCheckBox::indicator" in stylesheet
    assert "width: 16px" in stylesheet
    assert "subcontrol-position: top right" in stylesheet
    assert 'width="8" height="5"' in arrow_assets[0]
    assert "#657383" in arrow_assets[0]
    assert "#a9b2bc" in arrow_assets[2]
    assert "width: 8px; height: 5px" in stylesheet
    assert stylesheet.count("border-left: 1px solid #c7d0da") == 2
    assert stylesheet.count("background: #f7f9fb") >= 3
    assert "border-bottom: 1px solid #d8dfe6" in stylesheet
    assert "QComboBox::down-arrow" in stylesheet
    assert "QGroupBox#sectionContent" in stylesheet
    assert "QToolButton#sectionToggle:checked" in stylesheet
    assert 'width="6" height="10"' in disclosure_assets[0]
    assert "__SPIN_" not in stylesheet


def test_run_button_is_outside_scrolling_settings(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)

    assert panel.run_button.isAncestorOf(panel.scroll_area) is False
    assert panel.scroll_area.isAncestorOf(panel.run_button) is False
    assert panel.run_button.parentWidget().objectName() == "actionBar"


def test_sweep_case_count_and_single_point_step_state(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)

    assert panel.case_count.text() == "1 result"
    assert panel.alpha_fields[2].isEnabled() is True
    assert panel.alpha_fields[2].toolTip() == "Ignored when Start and End are the same."

    panel.alpha_fields[1].setValue(10.0)
    panel.alpha_fields[2].setValue(5.0)
    panel.beta_fields[1].setValue(10.0)
    panel.beta_fields[2].setValue(5.0)

    assert panel.case_count.text() == "9 results"
    assert panel.alpha_fields[2].isEnabled() is True
    assert panel.alpha_fields[2].toolTip() == "Increment between sweep values."


def test_detailed_overlay_option_is_opt_in(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)

    assert panel.viewer_options().detailed_overlay is False
    panel.detailed_overlay.setChecked(True)
    assert panel.viewer_options().detailed_overlay is True


def test_advanced_changes_show_pending_state_only_after_model_load(qtbot, tmp_path: Path) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)

    assert panel.advanced_status.isVisible() is False
    assert panel.apply_advanced_button.toolTip() == (
        "Load a model before reloading it with Advanced settings."
    )
    panel.axis_x.setCurrentIndex(panel.axis_x.findData("-x"))

    assert panel._advanced_dirty is False
    assert panel.advanced_status.isHidden() is True
    assert panel._section_toggles["Advanced"].text() == "Advanced"
    assert panel.apply_advanced_button.isEnabled() is False
    assert panel.apply_advanced_button.toolTip() == (
        "Load a model before reloading it with Advanced settings."
    )

    path = tmp_path / "model.step"
    path.touch()
    panel.set_file_paths((path,))
    panel.set_model(_model(path, component_names=("Body",)))
    panel.axis_x.setCurrentIndex(panel.axis_x.findData("x"))

    assert panel._advanced_dirty is True
    assert panel.advanced_status.isHidden() is False
    assert "changes not applied" in panel._section_toggles["Advanced"].text()
    assert panel.apply_advanced_button.isEnabled() is True


def test_control_panel_populates_step_components(qtbot, tmp_path: Path) -> None:
    path = tmp_path / "assembly.step"
    path.touch()
    panel = ControlPanel()
    qtbot.addWidget(panel)
    panel.set_file_paths((path,))
    panel.set_model(_model(path, component_names=("Body", "Wing")))

    panel._component_checkboxes[1].setChecked(False)
    panel.step_component_mode.setCurrentIndex(panel.step_component_mode.findData("subtract"))
    request = panel.request()

    assert request.step_components == (1,)
    assert request.step_component_mode == "subtract"
    assert panel.component_summary.text() == "1 of 2 components enabled."


def test_results_panel_displays_selects_and_exports_rows(qtbot, tmp_path: Path) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    row = _row()
    selected = []
    panel.selected_row_changed.connect(selected.append)

    panel.set_rows([row])
    panel.select_last_row()
    output = tmp_path / "rows.csv"
    panel.save_csv(output)

    assert panel.result_count.text() == "Rows: 1"
    assert selected == [row]
    assert output.read_text(encoding="utf-8").startswith("file,step_components")


def test_results_panel_restores_table_density(qtbot) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    toolbar = panel.findChild(QtWidgets.QWidget, "resultToolbar")
    margins = toolbar.layout().contentsMargins()

    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (10, 6, 10, 6)
    assert panel.table.alternatingRowColors() is True
    assert panel.table.verticalHeader().isVisible() is False
    assert panel.table.verticalHeader().defaultSectionSize() == 24


def test_results_panel_uses_empty_state_until_rows_exist(qtbot) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)

    assert panel.stack.currentWidget() is panel.empty_state
    assert panel.empty_title.text() == "No results yet"
    assert "Run Sweep" in panel.empty_message.text()

    panel.set_rows([_row()])

    assert panel.stack.currentWidget() is panel.table


def test_results_panel_keeps_all_field_names_left_aligned_and_discoverable(qtbot) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.set_rows([_row()])
    header = panel.table.horizontalHeader()

    assert panel.table.columnCount() == len(CSV_FIELDS)
    assert panel.table.textElideMode() == QtCore.Qt.TextElideMode.ElideRight
    assert header.sectionResizeMode(0) == QtWidgets.QHeaderView.ResizeMode.Interactive
    assert DISPLAY_FIELDS[:6] == [
        "file",
        "alpha_deg",
        "beta_deg",
        "roll_deg",
        "pitch_deg",
        "projected_area",
    ]
    for column_index, column in enumerate(DISPLAY_FIELDS):
        item = panel.table.horizontalHeaderItem(column_index)
        assert item.text() == RESULT_HEADER_LABELS.get(column, column.replace("_", " ").title())
        assert item.toolTip() == f"CSV field: {column}"
        assert item.textAlignment() & QtCore.Qt.AlignmentFlag.AlignLeft


def test_results_panel_cells_are_left_aligned_with_full_text_tooltips(qtbot) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    row = _row()
    panel.set_rows([row])
    file_column = DISPLAY_FIELDS.index("file")
    file_item = panel.table.item(0, file_column)

    assert file_item.textAlignment() & QtCore.Qt.AlignmentFlag.AlignLeft
    assert file_item.toolTip() == file_item.text()
    assert all(
        panel.table.columnWidth(column_index) == DEFAULT_COLUMN_WIDTH
        for column_index in range(len(CSV_FIELDS))
    )


def test_main_window_only_composes_gui_components(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(pyside_app, "ModelViewer", _FakeViewer)
    window = pyside_app.MainWindow()
    qtbot.addWidget(window)

    assert isinstance(window.controls, ControlPanel)
    assert isinstance(window.results, ResultsPanel)
    assert isinstance(window.viewer, _FakeViewer)
    assert len(Path("src/cadmetrics/gui/pyside_app.py").read_text().splitlines()) <= 400


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
