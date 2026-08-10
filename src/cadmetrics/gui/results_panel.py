from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6 import QtCore, QtWidgets

from cadmetrics.gui.export import write_rows_csv
from cadmetrics.gui.results_model import DISPLAY_FIELDS
from cadmetrics.gui.results_model import PRIMARY_DISPLAY_FIELDS as PRIMARY_DISPLAY_FIELDS
from cadmetrics.gui.results_model import RESULT_HEADER_LABELS as RESULT_HEADER_LABELS
from cadmetrics.gui.results_model import ResultsTableModel
from cadmetrics.types import MeasurementRow

DEFAULT_COLUMN_WIDTH = 130


class ResultsPanel(QtWidgets.QWidget):
    selected_row_changed = QtCore.Signal(object)
    error = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[MeasurementRow] = []
        self._protected_paths: tuple[Path, ...] = ()
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
        self.save_button.clicked.connect(self._choose_csv_path)
        toolbar_layout.addWidget(self.result_count)
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
        self._table_model = ResultsTableModel(self.table)
        self.table.setModel(self._table_model)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(DEFAULT_COLUMN_WIDTH)
        header.setMinimumSectionSize(70)
        header.setStretchLastSection(False)
        header.setDefaultAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.table.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        for column_index in range(len(DISPLAY_FIELDS)):
            self.table.setColumnWidth(
                column_index,
                DEFAULT_COLUMN_WIDTH,
            )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.selectionModel().currentRowChanged.connect(self._emit_selected_row)
        self.stack.addWidget(self.table)
        layout.addWidget(self.stack)
        self.set_busy(False)

    @property
    def rows(self) -> list[MeasurementRow]:
        return list(self._rows)

    def set_rows(
        self,
        rows: list[MeasurementRow],
        *,
        protected_paths: Iterable[str | Path] | None = None,
    ) -> None:
        self._rows = list(rows)
        if protected_paths is not None:
            self._protected_paths = tuple(Path(path) for path in protected_paths)
        self._table_model.set_rows(self._rows)
        self.result_count.setText(f"Rows: {len(rows)}")
        self.save_button.setEnabled(bool(rows))
        self.save_button.setToolTip(
            "Save all result columns to CSV." if rows else "Run a sweep before saving results."
        )
        self.stack.setCurrentWidget(self.table if rows else self.empty_state)

    def clear(self) -> None:
        self.set_rows([])

    def select_last_row(self) -> None:
        if self._rows:
            self.table.selectRow(len(self._rows) - 1)

    def set_busy(self, busy: bool) -> None:
        self.save_button.setEnabled(not busy and bool(self._rows))
        if busy and not self._rows:
            self.empty_title.setText("Calculating…")
            self.empty_message.setText("Results will appear here as soon as the sweep finishes.")
            self.stack.setCurrentWidget(self.empty_state)
        elif not self._rows:
            self.empty_title.setText("No results yet")
            self.empty_message.setText("Run Sweep to generate results.")

    def save_csv(self, path: str | Path) -> None:
        if not self._rows:
            raise ValueError("No calculation results to save.")
        write_rows_csv(path, self._rows, protected_paths=self._protected_paths)

    def _choose_csv_path(self) -> None:
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

    def _emit_selected_row(
        self,
        current: QtCore.QModelIndex,
        _previous: QtCore.QModelIndex,
    ) -> None:
        row = current.row()
        if 0 <= row < len(self._rows):
            self.selected_row_changed.emit(self._rows[row])
