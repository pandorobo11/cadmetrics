from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from PySide6 import QtCore

from cadmetrics.gui.gui_formatters import format_cell, format_model_file_label
from cadmetrics.gui.table_copy import tsv
from cadmetrics.result_schema import GUI_RESULT_FIELD_SPECS, RESULT_FIELD_SPECS, CsvValue
from cadmetrics.types import MeasurementRow

PRIMARY_DISPLAY_FIELDS = [
    spec.key for spec in GUI_RESULT_FIELD_SPECS if spec.gui_priority is not None
]
DISPLAY_FIELDS = [spec.key for spec in GUI_RESULT_FIELD_SPECS]
RESULT_HEADER_LABELS = {spec.key: spec.gui_label for spec in RESULT_FIELD_SPECS}

# Power of ``output_unit`` carried by each field, used to add units to column headers.
UNIT_POWERS = {
    **{key: 1 for key in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")},
    **{key: 1 for key in ("centroid_u", "centroid_v", "centroid_x", "centroid_y", "centroid_z")},
    **{
        key: 2
        for key in ("surface_area", "newly_exposed_surface_area", "base_area", "projected_area")
    },
    "volume": 3,
}
_UNIT_SUFFIXES = {1: "", 2: "²", 3: "³"}

SORT_ROLE = int(QtCore.Qt.ItemDataRole.UserRole) + 1
_DISPLAY_ROLE = int(QtCore.Qt.ItemDataRole.DisplayRole)
_TOOLTIP_ROLE = int(QtCore.Qt.ItemDataRole.ToolTipRole)
_ALIGNMENT_ROLE = int(QtCore.Qt.ItemDataRole.TextAlignmentRole)
_LEFT_ALIGNMENT = QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
_RIGHT_ALIGNMENT = QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
_FILE_COLUMN = DISPLAY_FIELDS.index("file")


def header_label(key: str, output_unit: str | None) -> str:
    """Return the GUI column header, with the unit derived from ``output_unit``."""
    label = RESULT_HEADER_LABELS[key]
    power = UNIT_POWERS.get(key)
    if power is None or not output_unit:
        return label
    return f"{label} ({output_unit}{_UNIT_SUFFIXES[power]})"


def rows_to_tsv(rows: Iterable[MeasurementRow], output_unit: str | None) -> str:
    """Serialize rows as tab-separated text with headers and 12 significant digits."""
    return tsv(
        [header_label(key, output_unit) for key in DISPLAY_FIELDS],
        ([spec.extract_value(row) for spec in GUI_RESULT_FIELD_SPECS] for row in rows),
    )


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _full_precision(value: CsvValue) -> str:
    if isinstance(value, float):
        return f"{value:.12g}"
    return "" if value is None else str(value)


def _file_label(value: CsvValue) -> str:
    if not value:
        return ""
    return format_model_file_label(Path(str(value)))


def _file_tooltip(value: CsvValue) -> str:
    if not value:
        return ""
    return "\n".join(part.strip() for part in str(value).split(";") if part.strip())


class ResultsTableModel(QtCore.QAbstractTableModel):
    """Expose measurement rows to Qt without materializing per-cell items."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[MeasurementRow] = []

    @property
    def rows(self) -> list[MeasurementRow]:
        return list(self._rows)

    @property
    def output_unit(self) -> str | None:
        return self._rows[0].output_unit if self._rows else None

    def row(self, index: int) -> MeasurementRow:
        return self._rows[index]

    def set_rows(self, rows: list[MeasurementRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def append_rows(self, rows: Sequence[MeasurementRow]) -> None:
        if not rows:
            return
        unit_changed = self.output_unit != rows[0].output_unit
        first = len(self._rows)
        self.beginInsertRows(QtCore.QModelIndex(), first, first + len(rows) - 1)
        self._rows.extend(rows)
        self.endInsertRows()
        if first == 0 or unit_changed:
            self.headerDataChanged.emit(
                QtCore.Qt.Orientation.Horizontal, 0, len(DISPLAY_FIELDS) - 1
            )

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
        if role not in {_DISPLAY_ROLE, _TOOLTIP_ROLE, _ALIGNMENT_ROLE, SORT_ROLE}:
            return None
        spec = GUI_RESULT_FIELD_SPECS[index.column()]
        value = spec.extract_value(self._rows[index.row()])
        if role == SORT_ROLE:
            return value
        if role == _ALIGNMENT_ROLE:
            return _RIGHT_ALIGNMENT if _is_number(value) else _LEFT_ALIGNMENT
        if index.column() == _FILE_COLUMN:
            return _file_label(value) if role == _DISPLAY_ROLE else _file_tooltip(value)
        if role == _TOOLTIP_ROLE:
            return _full_precision(value)
        return format_cell(value)

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
            return header_label(spec.key, self.output_unit)
        if role == _TOOLTIP_ROLE:
            return spec.gui_tooltip
        if role == _ALIGNMENT_ROLE:
            if self._rows and _is_number(spec.extract_value(self._rows[0])):
                return _RIGHT_ALIGNMENT
            return _LEFT_ALIGNMENT
        return None


class ResultsSortProxyModel(QtCore.QSortFilterProxyModel):
    """Sort on raw values so numbers order numerically and blanks stay together."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.setSortRole(SORT_ROLE)

    def lessThan(  # noqa: N802
        self,
        left: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        right: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> bool:
        left_value = left.data(SORT_ROLE)
        right_value = right.data(SORT_ROLE)
        if left_value is None or right_value is None:
            return left_value is None and right_value is not None
        if _is_number(left_value) and _is_number(right_value):
            return bool(left_value < right_value)
        if isinstance(left_value, bool) and isinstance(right_value, bool):
            return left_value < right_value
        return str(left_value).casefold() < str(right_value).casefold()
