from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

from PySide6 import QtCore, QtGui, QtWidgets

from cadmetrics.gui.export import write_rows_csv
from cadmetrics.gui.results_model import DISPLAY_FIELDS
from cadmetrics.gui.results_model import PRIMARY_DISPLAY_FIELDS as PRIMARY_DISPLAY_FIELDS
from cadmetrics.gui.results_model import RESULT_HEADER_LABELS as RESULT_HEADER_LABELS
from cadmetrics.gui.results_model import ResultsSortProxyModel, ResultsTableModel, rows_to_tsv
from cadmetrics.types import MeasurementRow

DEFAULT_COLUMN_WIDTH = 130
FILE_COLUMN_WIDTH = 180
# Room for the sort indicator, which sectionSizeHint does not include.
SORT_INDICATOR_ALLOWANCE = 18
STALE_MESSAGE = "Results are out of date — Run Sweep to update."


class _SelectedRowDelegate(QtWidgets.QStyledItemDelegate):
    """Keep row highlighting when Cocoa must receive a single selected cell."""

    def __init__(self, table: QtWidgets.QTableView) -> None:
        super().__init__(table)
        self._table = table

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        row_option = QtWidgets.QStyleOptionViewItem(option)
        if (
            self._table.selectionModel().hasSelection()
            and index.row() == self._table.currentIndex().row()
        ):
            row_option.state |= QtWidgets.QStyle.StateFlag.State_Selected
        super().paint(painter, row_option, index)


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
        # styles.py dims the table and styles this label via objectName / stale property.
        self.stale_label = QtWidgets.QLabel(STALE_MESSAGE)
        self.stale_label.setObjectName("resultsStaleLabel")
        self.stale_label.setVisible(False)
        toolbar_layout.addWidget(self.result_count)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(self.stale_label)
        toolbar_layout.addStretch(1)
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
        # Qt 6.11.1's Cocoa selectedChildren enumerator can invalidate sibling
        # accessible cell pointers while materializing a whole selected row.
        # Keep one native selected cell and paint the same full-row highlight.
        self._cocoa_cell_selection = sys.platform == "darwin"
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectItems
            if self._cocoa_cell_selection
            else QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        if self._cocoa_cell_selection:
            self.table.setItemDelegate(_SelectedRowDelegate(self.table))
            self.table.selectionModel().currentRowChanged.connect(
                lambda *_: self.table.viewport().update()
            )
            self.table.selectionModel().selectionChanged.connect(
                lambda *_: self.table.viewport().update()
            )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.selectionModel().currentRowChanged.connect(self._emit_selected_row)
        self.copy_action = QtGui.QAction("Copy", self.table)
        self.copy_action.setShortcut(QtGui.QKeySequence.StandardKey.Copy)
        self.copy_action.setShortcutContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.copy_action.triggered.connect(self.copy_selection)
        self.table.addAction(self.copy_action)
        self.stack.addWidget(self.table)
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
        self._set_stale(False)
        self._sync_rows()

    def append_rows(self, rows: list[MeasurementRow]) -> None:
        """Add rows computed so far without resetting the user's selection or sort."""
        if not rows:
            return
        self._rows.extend(rows)
        self._table_model.append_rows(rows)
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
        self._set_stale(stale)

    def has_selection(self) -> bool:
        return self._current_source_row() is not None

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

    def copy_selection(self) -> None:
        selection = self.table.selectionModel()
        proxy_rows = sorted({index.row() for index in selection.selectedIndexes()})
        if not proxy_rows:
            source_row = self._current_source_row()
            source_rows = [] if source_row is None else [source_row]
        else:
            source_rows = [
                self._sort_model.mapToSource(self._sort_model.index(row, 0)).row()
                for row in proxy_rows
            ]
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
        if rows:
            self._fit_header_widths()
            self.stack.setCurrentWidget(self.table)
        else:
            if self._busy:
                self.empty_title.setText(self._busy_title)
                self.empty_message.setText("Results will appear here as each case finishes.")
            else:
                self.empty_title.setText("No results yet")
                self.empty_message.setText("Run Sweep to generate results.")
            self.stack.setCurrentWidget(self.empty_state)
        self.rows_changed.emit()

    def _set_stale(self, stale: bool) -> None:
        if stale == self._stale:
            return
        self._stale = stale
        self.stale_label.setVisible(stale)
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
            self.selected_row_changed.emit(self._table_model.row(row))
