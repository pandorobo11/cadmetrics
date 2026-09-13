from __future__ import annotations

from PySide6 import QtCore

from cadmetrics.gui.gui_formatters import format_cell
from cadmetrics.result_schema import GUI_RESULT_FIELD_SPECS, RESULT_FIELD_SPECS
from cadmetrics.types import MeasurementRow

PRIMARY_DISPLAY_FIELDS = [
    spec.key for spec in GUI_RESULT_FIELD_SPECS if spec.gui_priority is not None
]
DISPLAY_FIELDS = [spec.key for spec in GUI_RESULT_FIELD_SPECS]
RESULT_HEADER_LABELS = {spec.key: spec.gui_label for spec in RESULT_FIELD_SPECS}

_DISPLAY_ROLE = int(QtCore.Qt.ItemDataRole.DisplayRole)
_TOOLTIP_ROLE = int(QtCore.Qt.ItemDataRole.ToolTipRole)
_ALIGNMENT_ROLE = int(QtCore.Qt.ItemDataRole.TextAlignmentRole)
_CELL_ALIGNMENT = QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter


class ResultsTableModel(QtCore.QAbstractTableModel):
    """Expose measurement rows to Qt without materializing per-cell items."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[MeasurementRow] = []

    @property
    def rows(self) -> list[MeasurementRow]:
        return list(self._rows)

    def set_rows(self, rows: list[MeasurementRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(
        self,
        parent: QtCore.QModelIndex | QtCore.QPersistentModelIndex = QtCore.QModelIndex(),
    ) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(
        self,
        parent: QtCore.QModelIndex | QtCore.QPersistentModelIndex = QtCore.QModelIndex(),
    ) -> int:
        return 0 if parent.isValid() else len(DISPLAY_FIELDS)

    def data(
        self,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        role: int = _DISPLAY_ROLE,
    ) -> object | None:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        if not 0 <= index.column() < len(DISPLAY_FIELDS):
            return None
        if role == _ALIGNMENT_ROLE:
            return _CELL_ALIGNMENT
        if role not in {_DISPLAY_ROLE, _TOOLTIP_ROLE}:
            return None
        spec = GUI_RESULT_FIELD_SPECS[index.column()]
        return format_cell(spec.extract_value(self._rows[index.row()]))

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = _DISPLAY_ROLE,
    ) -> object | None:
        if orientation != QtCore.Qt.Orientation.Horizontal:
            return None
        if not 0 <= section < len(DISPLAY_FIELDS):
            return None
        spec = GUI_RESULT_FIELD_SPECS[section]
        if role == _DISPLAY_ROLE:
            return spec.gui_label
        if role == _TOOLTIP_ROLE:
            return spec.gui_tooltip
        if role == _ALIGNMENT_ROLE:
            return _CELL_ALIGNMENT
        return None
