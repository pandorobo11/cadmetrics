from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6 import QtCore, QtWidgets

from cadmetrics.gui.export import write_rows_csv
from cadmetrics.gui.results_chart import AXES, IMAGE_SUFFIXES, ResultsChart
from cadmetrics.gui.results_model import DISPLAY_FIELDS
from cadmetrics.gui.results_model import PRIMARY_DISPLAY_FIELDS as PRIMARY_DISPLAY_FIELDS
from cadmetrics.gui.results_model import RESULT_HEADER_LABELS as RESULT_HEADER_LABELS
from cadmetrics.gui.results_model import (
    SORT_ROLE,
    ResultsSortProxyModel,
    ResultsTableModel,
    rows_to_tsv,
)
from cadmetrics.gui.table_copy import TableCopyActions, configure_row_selection, full_precision
from cadmetrics.types import MeasurementRow

DEFAULT_COLUMN_WIDTH = 130
FILE_COLUMN_WIDTH = 180
# Room for the sort indicator, which sectionSizeHint does not include.
SORT_INDICATOR_ALLOWANCE = 18
STALE_MESSAGE = "Results are out of date — Run Sweep to update."


class ResultsPanel(QtWidgets.QWidget):
    selected_row_changed = QtCore.Signal(object)
    rows_changed = QtCore.Signal()
    error = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[MeasurementRow] = []
        self._protected_paths: tuple[Path, ...] = ()
        self._busy = False
        self._busy_title = "Calculating…"
        self._stale = False
        self._attitude_mode = "alpha_beta"
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar = QtWidgets.QWidget()
        toolbar.setObjectName("resultToolbar")
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 6, 10, 6)
        self.result_count = QtWidgets.QLabel("Rows: 0")
        self.result_count.setObjectName("resultCountLabel")
        self.save_button = QtWidgets.QPushButton("Save CSV")
        self.save_button.setObjectName("secondaryButton")
        self.save_button.setToolTip("Run a sweep before saving results.")
        self.save_button.clicked.connect(self.choose_csv_path)
        self.save_image_button = QtWidgets.QPushButton("Save Image")
        self.save_image_button.setObjectName("secondaryButton")
        self.save_image_button.setToolTip("Save the chart as a PNG or SVG image.")
        self.save_image_button.clicked.connect(self.choose_image_path)
        # styles.py dims the table and styles this label via objectName / stale property.
        self.stale_label = QtWidgets.QLabel(STALE_MESSAGE)
        self.stale_label.setObjectName("resultsStaleLabel")
        self.stale_label.setVisible(False)
        self.table_view_button = self._view_toggle("Table", "Show results as a table.")
        self.chart_view_button = self._view_toggle(
            "Chart", "Plot projected area against the swept angle."
        )
        self.table_view_button.setChecked(True)
        view_group = QtWidgets.QButtonGroup(self)
        view_group.setExclusive(True)
        view_group.addButton(self.table_view_button)
        view_group.addButton(self.chart_view_button)
        self.chart_view_button.toggled.connect(lambda _checked: self._sync_rows())
        self.x_axis_label = QtWidgets.QLabel("X axis")
        self.x_axis_combo = QtWidgets.QComboBox()
        self.x_axis_combo.setObjectName("chartXAxisCombo")
        self.x_axis_combo.setToolTip(
            "Angle along the chart's x axis; each value of the other angle is one line. "
            "Auto puts the angle with more values on the x axis."
        )
        self.x_axis_combo.currentIndexChanged.connect(self._x_axis_changed)
        toolbar_layout.addWidget(self.result_count)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(self.table_view_button)
        toolbar_layout.addWidget(self.chart_view_button)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(self.x_axis_label)
        toolbar_layout.addWidget(self.x_axis_combo)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(self.stale_label)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.save_image_button)
        toolbar_layout.addWidget(self.save_button)
        layout.addWidget(toolbar)
        self.stack = QtWidgets.QStackedWidget()
        self.empty_state = QtWidgets.QWidget()
        empty_layout = QtWidgets.QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(24, 24, 24, 24)
        empty_layout.addStretch(1)
        self.empty_title = QtWidgets.QLabel("No results yet")
        self.empty_title.setObjectName("emptyStateTitle")
        self.empty_title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.empty_message = QtWidgets.QLabel("Run Sweep to generate results.")
        self.empty_message.setObjectName("emptyStateMessage")
        self.empty_message.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_message)
        empty_layout.addStretch(1)
        self.stack.addWidget(self.empty_state)

        self.chart = ResultsChart()
        self.chart.row_clicked.connect(self.select_source_row)
        self._fill_x_axis_choices()
        self.table = QtWidgets.QTableView()
        self.table.setProperty("stale", False)
        self._table_model = ResultsTableModel(self.table)
        self._sort_model = ResultsSortProxyModel(self.table)
        self._sort_model.setSourceModel(self._table_model)
        self.table.setModel(self._sort_model)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(DEFAULT_COLUMN_WIDTH)
        header.setMinimumSectionSize(70)
        header.setStretchLastSection(False)
        header.setDefaultAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.table.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        for column_index, key in enumerate(DISPLAY_FIELDS):
            self.table.setColumnWidth(
                column_index,
                FILE_COLUMN_WIDTH if key == "file" else DEFAULT_COLUMN_WIDTH,
            )
        # Every row of a sweep comes from the same model, which the control panel already
        # names; the file stays in copied rows and CSV.
        self.table.setColumnHidden(DISPLAY_FIELDS.index("file"), True)
        # Start in calculation order; clicking a header sorts through the proxy model.
        header.setSortIndicator(-1, QtCore.Qt.SortOrder.AscendingOrder)
        self.table.setSortingEnabled(True)
        header.setSortIndicatorShown(True)
        self.table.setAlternatingRowColors(True)
        self._cocoa_cell_selection = configure_row_selection(self.table)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.selectionModel().currentRowChanged.connect(self._emit_selected_row)
        self.copy_actions = TableCopyActions(
            self.table,
            copy_value=self.copy_value,
            copy_row=self.copy_selection,
            copy_all=self.copy_all_rows,
        )
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.chart)
        layout.addWidget(self.stack)
        self.set_busy(False)

    @property
    def rows(self) -> list[MeasurementRow]:
        return list(self._rows)

    @property
    def is_stale(self) -> bool:
        return self._stale

    @property
    def can_save(self) -> bool:
        return not self._busy and bool(self._rows)

    def set_attitude_mode(self, mode: str) -> None:
        """Set which angles the chart plots: those swept in this attitude mode."""
        if mode != self._attitude_mode:
            self._attitude_mode = mode
            self._fill_x_axis_choices()
        self.chart.set_rows(self._rows, mode)
        self._sync_chart_controls()

    def _x_axis_changed(self, _index: int) -> None:
        self.chart.set_x_field(self.x_axis_combo.currentData())
        self._sync_chart_controls()

    def _fill_x_axis_choices(self) -> None:
        """Offer Auto plus this mode's two swept angles; other modes have no chart axes."""
        with QtCore.QSignalBlocker(self.x_axis_combo):
            self.x_axis_combo.clear()
            self.x_axis_combo.addItem("Auto", None)
            for field, label in AXES.get(self._attitude_mode, ()):
                self.x_axis_combo.addItem(label, field)
        self.chart.set_x_field(None)
        self.x_axis_combo.setEnabled(self._attitude_mode in AXES)

    def set_rows(
        self,
        rows: list[MeasurementRow],
        *,
        protected_paths: Iterable[str | Path] | None = None,
    ) -> None:
        self._rows = list(rows)
        if protected_paths is not None:
            self._protected_paths = tuple(Path(path) for path in protected_paths)
        self._table_model.set_rows(list(self._rows))
        self.chart.set_selected(None)
        self.chart.set_rows(self._rows, self._attitude_mode)
        self._set_stale(False)
        self._sync_rows()

    def append_rows(self, rows: list[MeasurementRow]) -> None:
        """Add rows computed so far without resetting the user's selection or sort."""
        if not rows:
            return
        self._rows.extend(rows)
        self._table_model.append_rows(rows)
        self.chart.set_rows(self._rows, self._attitude_mode)
        self._set_stale(False)
        self._sync_rows()

    def set_protected_paths(self, protected_paths: Iterable[str | Path]) -> None:
        self._protected_paths = tuple(Path(path) for path in protected_paths)

    def clear(self) -> None:
        self.set_rows([])

    def mark_stale(self, stale: bool = True) -> None:
        """Keep rows visible but flag them as no longer matching the current inputs."""
        stale = stale and bool(self._rows)
        if stale and not self._stale:
            # Drop the current row so selecting any stale row re-emits it explicitly.
            self.table.selectionModel().clearSelection()
            self.table.setCurrentIndex(QtCore.QModelIndex())
            self.chart.set_selected(None)
        self._set_stale(stale)

    def has_selection(self) -> bool:
        return self._current_source_row() is not None

    def selected_row(self) -> MeasurementRow | None:
        row = self._current_source_row()
        return None if row is None else self._table_model.row(row)

    def select_last_row(self) -> None:
        if self._rows:
            self.select_source_row(len(self._rows) - 1)

    def select_source_row(self, row: int) -> None:
        """Select a row by its calculation order, whatever the table's sort."""
        if 0 <= row < len(self._rows):
            # The first visible column: the file column is hidden.
            column = next(c for c in range(len(DISPLAY_FIELDS)) if not self.table.isColumnHidden(c))
            proxy_index = self._sort_model.mapFromSource(self._table_model.index(row, column))
            if self._cocoa_cell_selection:
                self.table.setCurrentIndex(proxy_index)
            else:
                self.table.selectRow(proxy_index.row())

    def set_busy(self, busy: bool, *, title: str = "Calculating…") -> None:
        self._busy = busy
        self._busy_title = title
        self._sync_rows()

    def copy_value(self, index: QtCore.QModelIndex | QtCore.QPersistentModelIndex) -> None:
        """Copy one cell at full precision; the file column copies the full path."""
        if index.isValid():
            QtWidgets.QApplication.clipboard().setText(full_precision(index.data(SORT_ROLE)))

    def copy_selection(self) -> None:
        source_row = self._current_source_row()
        if source_row is not None:
            self._copy_rows([source_row])

    def copy_all_rows(self) -> None:
        """Copy every row in the table's current sort order."""
        self._copy_rows(
            [
                self._sort_model.mapToSource(self._sort_model.index(row, 0)).row()
                for row in range(self._sort_model.rowCount())
            ]
        )

    def _copy_rows(self, source_rows: list[int]) -> None:
        if not source_rows:
            return
        rows = [self._table_model.row(row) for row in source_rows]
        QtWidgets.QApplication.clipboard().setText(rows_to_tsv(rows, self._table_model.output_unit))

    def save_csv(self, path: str | Path) -> None:
        if not self._rows:
            raise ValueError("No calculation results to save.")
        write_rows_csv(path, self._rows, protected_paths=self._protected_paths)

    def choose_csv_path(self) -> None:
        if not self._rows:
            self.error.emit("No calculation results to save.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save CSV", "cadmetrics_results.csv", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            self.save_csv(path)
        except Exception as exc:
            self.error.emit(str(exc))

    def save_image(self, path: str | Path) -> None:
        self.chart.save_image(path)

    def choose_image_path(self) -> None:
        path, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Chart Image",
            "cadmetrics_chart.png",
            "PNG Image (*.png);;SVG Image (*.svg)",
        )
        if not path:
            return
        if Path(path).suffix.lower() not in IMAGE_SUFFIXES:
            path += ".svg" if selected_filter.startswith("SVG") else ".png"
            # The dialog only confirmed overwriting the name it returned, not this one.
            if Path(path).exists() and not self._confirm_overwrite(path):
                return
        try:
            self.save_image(path)
        except Exception as exc:
            self.error.emit(str(exc))

    def _confirm_overwrite(self, path: str) -> bool:
        answer = QtWidgets.QMessageBox.question(
            self,
            "Save Chart Image",
            f"{Path(path).name} already exists. Do you want to replace it?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        return answer == QtWidgets.QMessageBox.StandardButton.Yes

    @staticmethod
    def _view_toggle(text: str, tooltip: str) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setObjectName("viewButton")
        button.setText(text)
        button.setToolTip(tooltip)
        button.setCheckable(True)
        return button

    def _fit_header_widths(self) -> None:
        """Widen columns whose header, which carries the output unit, would be clipped."""
        header = self.table.horizontalHeader()
        for section in range(header.count()):
            needed = header.sectionSizeHint(section) + SORT_INDICATOR_ALLOWANCE
            if header.sectionSize(section) < needed:
                header.resizeSection(section, needed)

    def _sync_rows(self) -> None:
        rows = bool(self._rows)
        self.result_count.setText(f"Rows: {len(self._rows):,}")
        self.save_button.setEnabled(self.can_save)
        if self._busy:
            tooltip = "Saving is available when the current operation finishes."
        elif not rows:
            tooltip = "Run a sweep before saving results."
        elif self._stale:
            tooltip = "Save the out-of-date results to CSV."
        else:
            tooltip = "Save all result columns to CSV."
        self.save_button.setToolTip(tooltip)
        self._sync_chart_controls()
        if rows:
            self._fit_header_widths()
            chart = self.chart_view_button.isChecked()
            self.stack.setCurrentWidget(self.chart if chart else self.table)
        else:
            if self._busy:
                self.empty_title.setText(self._busy_title)
                self.empty_message.setText("Results will appear here as each case finishes.")
            else:
                self.empty_title.setText("No results yet")
                self.empty_message.setText("Run Sweep to generate results.")
            self.stack.setCurrentWidget(self.empty_state)
        self.rows_changed.emit()

    def _sync_chart_controls(self) -> None:
        chart_shown = bool(self._rows) and self.chart_view_button.isChecked()
        self.x_axis_label.setVisible(chart_shown)
        self.x_axis_combo.setVisible(chart_shown)
        self.save_image_button.setVisible(chart_shown)
        self.save_image_button.setEnabled(not self._busy and bool(self.chart.data.series))

    def _set_stale(self, stale: bool) -> None:
        if stale == self._stale:
            return
        self._stale = stale
        self.stale_label.setVisible(stale)
        self.chart.set_stale(stale)
        self.table.setProperty("stale", stale)
        style = self.table.style()
        style.unpolish(self.table)
        style.polish(self.table)
        self.table.viewport().update()
        self._sync_rows()

    def _current_source_row(self) -> int | None:
        current = self.table.currentIndex()
        if not current.isValid() or not self.table.selectionModel().hasSelection():
            return None
        row = self._sort_model.mapToSource(current).row()
        return row if 0 <= row < len(self._rows) else None

    def _emit_selected_row(
        self,
        current: QtCore.QModelIndex,
        _previous: QtCore.QModelIndex,
    ) -> None:
        if not current.isValid():
            return
        row = self._sort_model.mapToSource(current).row()
        if 0 <= row < len(self._rows):
            self.chart.set_selected(row)
            self.selected_row_changed.emit(self._table_model.row(row))
