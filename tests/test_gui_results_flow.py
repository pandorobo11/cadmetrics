from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from threading import Event

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6 import QtCore, QtGui, QtWidgets

import cadmetrics.gui.calculation_controller as calculation_controller
import cadmetrics.gui.pyside_app as pyside_app
import cadmetrics.gui.results_panel as results_panel
from cadmetrics.gui.calculation_controller import CalculationController
from cadmetrics.gui.gui_types import OperationState
from cadmetrics.gui.jobs import CalculationRequest, run_calculation
from cadmetrics.gui.results_model import DISPLAY_FIELDS, ResultsTableModel, header_label
from cadmetrics.gui.results_panel import ResultsPanel
from cadmetrics.types import MeasurementRow, ModelData

_RIGHT = QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
_LEFT = QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter


class _FakeViewer(QtWidgets.QWidget):
    error = QtCore.Signal(str)
    message = QtCore.Signal(str)
    base_face_available = QtCore.Signal(bool)
    newly_exposed_surface_available = QtCore.Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.result_calls = []
        self.requests = []

    def set_options(self, options) -> None:
        pass

    def set_request(self, request) -> None:
        self.requests.append(request)

    def set_model(self, model) -> None:
        pass

    def set_component_selection(self, selection) -> None:
        pass

    def set_result(self, row, request, *, align_camera=False) -> None:
        self.result_calls.append((row, request, align_camera))

    def choose_and_save_image(self) -> None:
        pass


@pytest.fixture
def window(qtbot, monkeypatch):
    monkeypatch.setattr(pyside_app, "ModelViewer", _FakeViewer)
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *args: None)
    main_window = pyside_app.MainWindow()
    qtbot.addWidget(main_window)
    return main_window


def _calculated_window(window, tmp_path: Path, rows: list[MeasurementRow] | None = None):
    source = tmp_path / "model.stl"
    source.touch()
    window.controls.set_file_paths((source,))
    request = window.controls.request()
    window._request = request
    window._results_request = request
    window._on_results_ready(rows if rows is not None else [_row()])
    return request


# 1. Empty-state text always matches the panel state.


@pytest.mark.parametrize("reset", ["clear", "set_rows", "set_busy"])
def test_empty_state_text_resets_after_busy(qtbot, reset: str) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.set_busy(True)
    assert panel.empty_title.text() == "Calculating…"

    if reset == "clear":
        panel.set_busy(False)
        panel.set_rows([_row()])
        panel.clear()
    elif reset == "set_rows":
        panel.set_busy(False)
        panel.set_rows([])
    else:
        panel.set_busy(False)

    assert panel.empty_title.text() == "No results yet"
    assert panel.empty_message.text() == "Run Sweep to generate results."
    assert panel.stack.currentWidget() is panel.empty_state


def test_empty_state_clears_while_busy_keeps_busy_text(qtbot) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.set_rows([_row()])
    panel.set_busy(True, title="Loading model…")
    panel.clear()

    assert panel.empty_title.text() == "Loading model…"
    assert panel.stack.currentWidget() is panel.empty_state


def test_main_window_empty_state_after_model_load_is_not_calculating(
    window, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(window.controller, "load_only", lambda request: None)
    _calculated_window(window, tmp_path)
    window.controls.set_file_paths((tmp_path / "model.stl",))
    window._load_model(window.controls.request())
    window._on_state_changed(OperationState.LOADING)
    assert window.results.empty_title.text() == "Loading model…"
    window._on_state_changed(OperationState.IDLE)
    assert window.results.empty_title.text() == "No results yet"


# 2 + 3. Stale results instead of silently clearing them.


def test_input_edit_keeps_results_as_stale_and_updates_status(window, tmp_path) -> None:
    _calculated_window(window, tmp_path)
    assert window.status.text() == "Done: 1 row(s)"
    assert window.results.stale_label.objectName() == "resultsStaleLabel"
    assert window.results.stale_label.isHidden()
    assert window.results.table.property("stale") is False

    window.controls.alpha_fields[1].setValue(10.0)

    assert window.results.rows == [_row()]
    assert window.results.is_stale
    assert not window.results.stale_label.isHidden()
    assert window.results.stale_label.text() == ("Results are out of date — Run Sweep to update.")
    assert window.results.table.property("stale") is True
    assert "out of date" in window.status.text()
    assert "Done" not in window.status.text()
    assert window.viewer.result_calls[-1][0] is None

    window.controls.alpha_fields[1].setValue(0.0)

    assert not window.results.is_stale
    assert window.results.table.property("stale") is False
    assert "out of date" not in window.status.text()


def test_selecting_stale_row_renders_it_with_its_own_request(window, tmp_path) -> None:
    rows = [replace(_row(), alpha_deg=0.0), replace(_row(), alpha_deg=5.0)]
    original = _calculated_window(window, tmp_path, rows)

    window.controls.output_unit.setCurrentText("mm")
    assert window.results.is_stale
    assert window._request != original
    # Going stale drops the current row so any row can be picked again.
    assert not window.results.has_selection()

    window.results.table.setCurrentIndex(window.results.table.model().index(1, 0))

    row, request, _ = window.viewer.result_calls[-1]
    assert row is rows[1]
    assert request == original


def test_stale_results_can_be_saved_to_csv(window, tmp_path) -> None:
    _calculated_window(window, tmp_path)
    window.controls.alpha_fields[1].setValue(10.0)
    assert window.results.is_stale
    assert window.results.save_button.isEnabled()
    assert window.save_csv_action.isEnabled()

    output = tmp_path / "stale.csv"
    window.results.save_csv(output)

    with output.open(encoding="utf-8", newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 1


def test_loading_another_model_clears_results(window, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(window.controller, "load_only", lambda request: None)
    _calculated_window(window, tmp_path)
    other = tmp_path / "other.stl"
    other.touch()
    window.controls.set_file_paths((other,))
    window._load_model(window.controls.request())

    assert window.results.rows == []
    assert not window.results.is_stale
    assert window.results.stale_label.isHidden()


def test_new_rows_clear_stale_state(qtbot) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.set_rows([_row()])
    panel.mark_stale()
    assert panel.is_stale

    panel.set_rows([_row()])

    assert not panel.is_stale
    assert panel.table.property("stale") is False


# 4. Progress is reported only once.


def test_progress_message_is_shown_only_in_action_bar(window, monkeypatch) -> None:
    messages = []
    monkeypatch.setattr(window.controls, "set_operation_message", messages.append)
    window._on_state_changed(OperationState.CALCULATING)

    window._on_progress(3, 10, "alpha=2, beta=0")

    assert messages == ["Sweep 3 of 10 · alpha=2, beta=0"]
    assert "Sweep" not in window.status.text()
    assert (window.progress_bar.value(), window.progress_bar.maximum()) == (3, 10)


# 5. Rows stream into the table while the sweep runs.


def test_run_calculation_reports_each_row(monkeypatch) -> None:
    rows = [replace(_row(), alpha_deg=float(index)) for index in range(3)]

    def fake_sweep(model, *, progress_callback, cancel_callback, **_kwargs):
        for index, row in enumerate(rows, start=1):
            progress_callback(index, len(rows), row)
        return rows

    monkeypatch.setattr("cadmetrics.gui.jobs.sweep_model", fake_sweep)
    received = []

    result = run_calculation(
        CalculationRequest(file=Path("model.stl")), model=_model(), row_callback=received.append
    )

    assert result == rows
    assert received == rows


def test_run_calculation_reports_vector_row(monkeypatch) -> None:
    row = _row()
    monkeypatch.setattr("cadmetrics.gui.jobs.project_model", lambda *args, **kwargs: row)
    received = []

    run_calculation(
        CalculationRequest(file=Path("model.stl"), attitude_mode="vector"),
        model=_model(),
        row_callback=received.append,
    )

    assert received == [row]


@pytest.mark.parametrize(("interval", "expected_batches"), [(0.0, 3), (60.0, 1)])
def test_controller_streams_rows_in_batches(
    qtbot, monkeypatch, interval: float, expected_batches: int
) -> None:
    rows = [replace(_row(), alpha_deg=float(index)) for index in range(3)]

    def fake_calculate(request, *, model, progress_callback, cancel_callback, row_callback):
        for row in rows:
            row_callback(row)
        return rows

    monkeypatch.setattr(calculation_controller, "ROW_BATCH_INTERVAL_SEC", interval)
    monkeypatch.setattr(calculation_controller, "load_model_for_request", lambda _: _model())
    monkeypatch.setattr(calculation_controller, "run_calculation", fake_calculate)
    controller = CalculationController()
    batches = []
    events = []
    controller.rows_appended.connect(lambda batch: (batches.append(batch), events.append("rows")))
    controller.results_ready.connect(lambda _rows: events.append("done"))

    controller.calculate(CalculationRequest(file=Path("model.stl")))
    qtbot.waitUntil(lambda: controller.state is OperationState.IDLE)

    assert len(batches) == expected_batches
    assert [row for batch in batches for row in batch] == rows
    assert events[-1] == "done"


def test_controller_keeps_completed_rows_on_cancel(qtbot, monkeypatch) -> None:
    rows = [replace(_row(), alpha_deg=float(index)) for index in range(2)]
    started = Event()
    release = Event()

    def fake_calculate(request, *, model, progress_callback, cancel_callback, row_callback):
        for row in rows:
            row_callback(row)
        started.set()
        release.wait(timeout=2)
        cancel_callback()
        return rows

    monkeypatch.setattr(calculation_controller, "ROW_BATCH_INTERVAL_SEC", 60.0)
    monkeypatch.setattr(calculation_controller, "load_model_for_request", lambda _: _model())
    monkeypatch.setattr(calculation_controller, "run_calculation", fake_calculate)
    controller = CalculationController()
    appended = []
    cancelled = []
    controller.rows_appended.connect(appended.extend)
    controller.cancelled.connect(lambda: cancelled.append(True))

    controller.calculate(CalculationRequest(file=Path("model.stl")))
    try:
        qtbot.waitUntil(lambda: started.is_set() and controller.state is OperationState.CALCULATING)
        controller.cancel()
    finally:
        release.set()
    qtbot.waitUntil(lambda: controller.state is OperationState.IDLE)

    assert cancelled == [True]
    assert appended == rows


def test_main_window_appends_streamed_rows_and_keeps_them_on_cancel(window, tmp_path) -> None:
    source = tmp_path / "model.stl"
    source.touch()
    window.controls.set_file_paths((source,))
    request = window.controls.request()
    window._request = request
    window._results_request = request
    window._calculation_running = True
    window._on_state_changed(OperationState.CALCULATING)
    first = [replace(_row(), alpha_deg=0.0)]
    second = [replace(_row(), alpha_deg=1.0), replace(_row(), alpha_deg=2.0)]

    window._on_rows_appended(first)
    assert window.results.rows == first
    assert window.results.stack.currentWidget() is window.results.table
    window._on_rows_appended(second)
    assert window.results.rows == first + second
    assert window.results.result_count.text() == "Rows: 3"

    window._on_cancelled()
    window._on_state_changed(OperationState.IDLE)

    assert window.results.rows == first + second
    assert "kept 3" in window.status.text()
    assert window.results.save_button.isEnabled()


def test_main_window_final_results_do_not_reset_streamed_selection(window, tmp_path) -> None:
    source = tmp_path / "model.stl"
    source.touch()
    window.controls.set_file_paths((source,))
    window._request = window._results_request = window.controls.request()
    rows = [replace(_row(), alpha_deg=float(index)) for index in range(3)]
    window._on_rows_appended(rows)
    window.results.table.setCurrentIndex(window.results.table.model().index(0, 0))

    window._on_results_ready(rows)

    assert window.viewer.result_calls[-1][0] is rows[0]
    assert window.results.table.currentIndex().row() == 0


# 6. File menu, shortcuts, and drag and drop.


def test_file_menu_actions_and_shortcuts(window, monkeypatch) -> None:
    file_menu = window.menuBar().actions()[0]
    assert file_menu.text() == "File"
    texts = [action.text() for action in file_menu.menu().actions() if not action.isSeparator()]
    assert texts == ["Open…", "Run Sweep", "Cancel", "Save CSV…", "Save View Image…"]
    assert window.open_action.shortcut() == QtGui.QKeySequence(QtGui.QKeySequence.StandardKey.Open)
    assert window.run_action.shortcut() == QtGui.QKeySequence("Ctrl+R")
    assert window.save_csv_action.shortcut() == QtGui.QKeySequence(
        QtGui.QKeySequence.StandardKey.Save
    )
    assert window.cancel_action.shortcut() == QtGui.QKeySequence("Ctrl+.")

    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileNames", lambda *args, **kwargs: ([], ""))
    opened = []
    window.controls.browse_button.clicked.connect(lambda: opened.append(True))
    window.open_action.trigger()
    assert opened == [True]


def test_run_action_clicks_only_enabled_run_button(window) -> None:
    clicks = []
    window.controls.run_button.clicked.connect(lambda: clicks.append(True))
    window.controls.run_button.setEnabled(False)
    window._run_sweep()
    assert clicks == []

    window.controls.run_button.setEnabled(True)
    window._run_sweep()
    assert clicks == [True]


def test_cancel_action_is_enabled_only_while_calculating(window, monkeypatch) -> None:
    for state in OperationState:
        monkeypatch.setattr(type(window.controller), "state", property(lambda _self: state))
        window._on_state_changed(state)
        assert window.cancel_action.isEnabled() is (state is OperationState.CALCULATING)
        assert window.run_action.isEnabled() is (state is OperationState.IDLE)


def test_save_action_follows_results(window, tmp_path, monkeypatch) -> None:
    assert not window.save_csv_action.isEnabled()
    _calculated_window(window, tmp_path)
    assert window.save_csv_action.isEnabled()
    chosen = []
    monkeypatch.setattr(window.results, "choose_csv_path", lambda: chosen.append(True))
    window.save_csv_action.trigger()
    assert chosen == [True]


def test_drop_model_files_loads_through_existing_path(window, monkeypatch, tmp_path) -> None:
    paths = (tmp_path / "body.step", tmp_path / "wing.stp")
    for path in paths:
        path.touch()
    loads = []
    monkeypatch.setattr(window.controller, "load_only", loads.append)
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(path)) for path in paths])
    position = QtCore.QPointF(10, 10)
    actions = QtCore.Qt.DropAction.CopyAction
    buttons = QtCore.Qt.MouseButton.NoButton
    modifiers = QtCore.Qt.KeyboardModifier.NoModifier

    enter = QtGui.QDragEnterEvent(position.toPoint(), actions, mime, buttons, modifiers)
    window.dragEnterEvent(enter)
    assert enter.isAccepted()
    window.dropEvent(QtGui.QDropEvent(position, actions, mime, buttons, modifiers))

    assert window.controls.file_paths == paths
    assert len(loads) == 1
    assert loads[0].file == paths


def test_drop_rejects_non_model_files(window, monkeypatch, tmp_path) -> None:
    text = tmp_path / "notes.txt"
    text.touch()
    loads = []
    monkeypatch.setattr(window.controller, "load_only", loads.append)
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(text))])
    enter = QtGui.QDragEnterEvent(
        QtCore.QPoint(10, 10),
        QtCore.Qt.DropAction.CopyAction,
        mime,
        QtCore.Qt.MouseButton.NoButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
    )

    window.dragEnterEvent(enter)

    assert not enter.isAccepted()
    assert window.load_dropped_files(()) is False
    assert loads == []


# 7. Result table presentation, sorting, and copying.


def test_table_shows_file_name_with_full_path_tooltip(qtbot) -> None:
    model = ResultsTableModel()
    model.set_rows(
        [
            replace(_row(), file="/Users/someone/models/aircraft.step"),
            replace(_row(), file="/a/body.step; /a/wing.step"),
        ]
    )
    column = DISPLAY_FIELDS.index("file")
    tooltip = QtCore.Qt.ItemDataRole.ToolTipRole

    assert model.data(model.index(0, column)) == "aircraft.step"
    assert model.data(model.index(0, column), tooltip) == "/Users/someone/models/aircraft.step"
    assert model.data(model.index(1, column)) == "body.step + wing.step"
    assert model.data(model.index(1, column), tooltip) == "/a/body.step\n/a/wing.step"


def test_table_right_aligns_numbers_with_six_significant_digits() -> None:
    model = ResultsTableModel()
    model.set_rows([replace(_row(), projected_area=1.0 / 3.0)])
    area = DISPLAY_FIELDS.index("projected_area")
    file_column = DISPLAY_FIELDS.index("file")
    alignment = QtCore.Qt.ItemDataRole.TextAlignmentRole
    horizontal = QtCore.Qt.Orientation.Horizontal

    assert model.data(model.index(0, area)) == "0.333333"
    model.set_rows([replace(_row(), centroid_u=-0.0)])
    assert model.data(model.index(0, DISPLAY_FIELDS.index("centroid_u"))) == "0"
    model.set_rows([replace(_row(), projected_area=1.0 / 3.0)])
    assert model.data(model.index(0, area), QtCore.Qt.ItemDataRole.ToolTipRole) == (
        "0.333333333333"
    )
    assert model.data(model.index(0, area), alignment) == _RIGHT
    assert model.data(model.index(0, file_column), alignment) == _LEFT
    assert model.headerData(area, horizontal, alignment) == _RIGHT


def test_csv_export_keeps_full_precision(qtbot, tmp_path) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.set_rows([replace(_row(), projected_area=1.0 / 3.0)])
    output = tmp_path / "rows.csv"
    panel.save_csv(output)
    with output.open(encoding="utf-8", newline="") as stream:
        saved = next(csv.DictReader(stream))
    assert float(saved["projected_area"]) == pytest.approx(1.0 / 3.0, rel=1e-15)


@pytest.mark.parametrize(("unit", "suffix"), [("m", "m"), ("mm", "mm")])
def test_headers_include_units_from_output_unit(unit: str, suffix: str) -> None:
    model = ResultsTableModel()
    horizontal = QtCore.Qt.Orientation.Horizontal
    area = DISPLAY_FIELDS.index("projected_area")
    assert model.headerData(area, horizontal) == "Projected area"

    model.append_rows([replace(_row(), output_unit=unit)])

    assert model.headerData(area, horizontal) == f"Projected area ({suffix}²)"
    assert model.headerData(DISPLAY_FIELDS.index("volume"), horizontal) == f"Volume ({suffix}³)"
    assert (
        model.headerData(DISPLAY_FIELDS.index("centroid_x"), horizontal) == f"Centroid X ({suffix})"
    )
    assert model.headerData(DISPLAY_FIELDS.index("alpha_deg"), horizontal) == "Alpha (°)"
    assert header_label("x_min", unit) == f"X min ({suffix})"


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_sorting_keeps_selection_mapped_to_source_rows(qtbot, monkeypatch, platform) -> None:
    monkeypatch.setattr(results_panel.sys, "platform", platform)
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    rows = [
        replace(_row(), alpha_deg=0.0, projected_area=3.0),
        replace(_row(), alpha_deg=5.0, projected_area=1.0),
        replace(_row(), alpha_deg=10.0, projected_area=2.0, volume=None),
    ]
    selected = []
    panel.selected_row_changed.connect(selected.append)
    panel.set_rows(rows)
    assert panel.table.isSortingEnabled()
    view_model = panel.table.model()
    alpha = DISPLAY_FIELDS.index("alpha_deg")
    assert [view_model.index(row, alpha).data() for row in range(3)] == ["0", "5", "10"]

    panel.table.sortByColumn(
        DISPLAY_FIELDS.index("projected_area"), QtCore.Qt.SortOrder.AscendingOrder
    )

    assert [view_model.index(row, alpha).data() for row in range(3)] == ["5", "10", "0"]
    panel.select_last_row()
    assert selected[-1] is rows[-1]
    assert panel.table.currentIndex().row() == 1
    panel.table.setCurrentIndex(view_model.index(0, 0))
    assert selected[-1] is rows[1]
    expected = 1 if platform == "darwin" else len(DISPLAY_FIELDS)
    assert len(panel.table.selectionModel().selectedIndexes()) == expected

    panel.table.sortByColumn(DISPLAY_FIELDS.index("volume"), QtCore.Qt.SortOrder.AscendingOrder)
    assert view_model.index(0, alpha).data() == "10"

    panel.append_rows([replace(_row(), alpha_deg=15.0, volume=0.5)])
    assert view_model.index(1, alpha).data() == "15"


def test_copy_selected_row_as_tsv(qtbot) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    rows = [
        replace(_row(), file="/models/first.stl", alpha_deg=0.0),
        replace(_row(), file="/models/second.stl", alpha_deg=7.5, projected_area=1.0 / 3.0),
    ]
    panel.set_rows(rows)
    panel.select_last_row()
    clipboard = QtWidgets.QApplication.clipboard()
    clipboard.clear()

    assert panel.copy_action.shortcut() == QtGui.QKeySequence(QtGui.QKeySequence.StandardKey.Copy)
    panel.copy_action.trigger()

    lines = clipboard.text().splitlines()
    assert len(lines) == 2
    header = lines[0].split("\t")
    values = lines[1].split("\t")
    assert len(header) == len(values) == len(DISPLAY_FIELDS)
    assert header[DISPLAY_FIELDS.index("projected_area")] == "Projected area (m²)"
    assert values[DISPLAY_FIELDS.index("file")] == "/models/second.stl"
    assert values[DISPLAY_FIELDS.index("alpha_deg")] == "7.5"
    assert values[DISPLAY_FIELDS.index("projected_area")] == "0.333333333333"


def _model() -> ModelData:
    return ModelData(
        path=Path("model.stl"),
        source_format="stl",
        vertices=np.empty((0, 3), dtype=float),
        faces=np.empty((0, 3), dtype=np.int64),
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
        alpha_deg=0.0,
        beta_deg=0.0,
        volume=1.0,
        surface_area=6.0,
        projected_area=1.0,
        is_watertight=True,
    )
