from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from cadmetrics.cli import CSV_FIELDS
from cadmetrics.gui.export import write_rows_csv
from cadmetrics.gui.gui_formatters import format_cell
from cadmetrics.types import MeasurementRow

DEFAULT_COLUMN_WIDTH = 130


class ResultsPanel(QtWidgets.QWidget):
    selected_row_changed = QtCore.Signal(object)
    error = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[MeasurementRow] = []
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
        self.save_button.clicked.connect(self._choose_csv_path)
        toolbar_layout.addWidget(self.result_count)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.save_button)
        layout.addWidget(toolbar)
        self.table = QtWidgets.QTableWidget(0, len(CSV_FIELDS))
        self.table.setHorizontalHeaderLabels(CSV_FIELDS)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(DEFAULT_COLUMN_WIDTH)
        header.setMinimumSectionSize(70)
        header.setStretchLastSection(False)
        header.setDefaultAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.table.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        for column_index, column in enumerate(CSV_FIELDS):
            header_item = self.table.horizontalHeaderItem(column_index)
            if header_item is None:
                raise RuntimeError(f"Could not create table header for {column}")
            header_item.setTextAlignment(
                QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
            )
            header_item.setToolTip(column)
            self.table.setColumnWidth(
                column_index,
                DEFAULT_COLUMN_WIDTH,
            )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.itemSelectionChanged.connect(self._emit_selected_row)
        layout.addWidget(self.table)
        self.set_busy(False)

    @property
    def rows(self) -> list[MeasurementRow]:
        return list(self._rows)

    def set_rows(self, rows: list[MeasurementRow]) -> None:
        self._rows = list(rows)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = row.to_csv_row()
            for column_index, column in enumerate(CSV_FIELDS):
                text = format_cell(values[column])
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(
                    QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
                )
                item.setToolTip(text)
                self.table.setItem(
                    row_index,
                    column_index,
                    item,
                )
        self.result_count.setText(f"Rows: {len(rows)}")
        self.save_button.setEnabled(bool(rows))

    def clear(self) -> None:
        self.set_rows([])

    def select_last_row(self) -> None:
        if self._rows:
            self.table.selectRow(len(self._rows) - 1)

    def set_busy(self, busy: bool) -> None:
        self.save_button.setEnabled(not busy and bool(self._rows))

    def save_csv(self, path: str | Path) -> None:
        if not self._rows:
            raise ValueError("No calculation results to save.")
        write_rows_csv(path, self._rows)

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

    def _emit_selected_row(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._rows):
            self.selected_row_changed.emit(self._rows[row])
