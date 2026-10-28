"""Row selection and clipboard copying shared by the result tables."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable, Sequence

from PySide6 import QtCore, QtGui, QtWidgets

from cadmetrics.result_schema import CsvValue


def full_precision(value: CsvValue) -> str:
    """Return a copied cell: 12 significant digits, on one line, with no tabs."""
    text = f"{value:.12g}" if isinstance(value, float) else "" if value is None else str(value)
    return text.replace("\t", " ").replace("\n", " ")


def tsv(header: Sequence[str], rows: Iterable[Sequence[CsvValue]]) -> str:
    """Serialize a header and rows as tab-separated text for pasting into a spreadsheet."""
    lines = ["\t".join(header)]
    lines.extend("\t".join(full_precision(value) for value in row) for row in rows)
    return "\n".join(lines) + "\n"


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


def configure_row_selection(table: QtWidgets.QTableView) -> bool:
    """Select one row at a time; return True when it is a single cell painted as a row.

    Qt 6.11.1's Cocoa selectedChildren enumerator can invalidate sibling accessible cell
    pointers while materializing a whole selected row. On macOS, keep one native selected
    cell and paint the same full-row highlight.
    """
    cocoa = sys.platform == "darwin"
    table.setSelectionBehavior(
        QtWidgets.QAbstractItemView.SelectionBehavior.SelectItems
        if cocoa
        else QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
    )
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    if cocoa:
        table.setItemDelegate(_SelectedRowDelegate(table))
        table.selectionModel().currentRowChanged.connect(lambda *_: table.viewport().update())
        table.selectionModel().selectionChanged.connect(lambda *_: table.viewport().update())
    return cocoa


class TableCopyActions:
    """Copy the clicked value, the selected row, or every row, from shortcuts or a menu.

    ``copy_value`` receives the model index under the pointer, or the current index when
    the value is copied from the keyboard.
    """

    def __init__(
        self,
        table: QtWidgets.QTableView,
        *,
        copy_value: Callable[[QtCore.QModelIndex | QtCore.QPersistentModelIndex], None],
        copy_row: Callable[[], None],
        copy_all: Callable[[], None],
    ) -> None:
        self._table = table
        self._copy_value = copy_value
        self._clicked = QtCore.QPersistentModelIndex()
        self.copy_value = self._action("Copy Value", self._copy_clicked_value)
        self.copy_row = self._action("Copy Row", copy_row, QtGui.QKeySequence.StandardKey.Copy)
        self.copy_all = self._action("Copy All Rows", copy_all, QtGui.QKeySequence("Ctrl+Shift+C"))
        table.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_menu)

    def _action(
        self,
        text: str,
        slot: Callable[[], None],
        shortcut: QtGui.QKeySequence | QtGui.QKeySequence.StandardKey | None = None,
    ) -> QtGui.QAction:
        action = QtGui.QAction(text, self._table)
        if shortcut is not None:
            action.setShortcut(shortcut)
            action.setShortcutContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            # Show the shortcut in the menu as well as handling the key on the table.
            action.setShortcutVisibleInContextMenu(True)
            self._table.addAction(action)
        action.triggered.connect(lambda _checked=False: slot())
        return action

    def menu(self, index: QtCore.QModelIndex) -> QtWidgets.QMenu:
        """Build the context menu for a click on ``index``."""
        self._clicked = QtCore.QPersistentModelIndex(index)
        has_rows = self._table.model().rowCount() > 0
        self.copy_value.setEnabled(index.isValid())
        self.copy_row.setEnabled(index.isValid() or self._table.currentIndex().isValid())
        self.copy_all.setEnabled(has_rows)
        menu = QtWidgets.QMenu(self._table)
        menu.addAction(self.copy_value)
        menu.addAction(self.copy_row)
        menu.addSeparator()
        menu.addAction(self.copy_all)
        # Menu availability must not leave the table shortcuts disabled afterwards.
        menu.aboutToHide.connect(self._enable_shortcuts)
        return menu

    def _enable_shortcuts(self) -> None:
        self.copy_row.setEnabled(True)
        self.copy_all.setEnabled(True)

    def _show_menu(self, position: QtCore.QPoint) -> None:
        menu = self.menu(self._table.indexAt(position))
        menu.exec(self._table.viewport().mapToGlobal(position))
        menu.deleteLater()

    def _copy_clicked_value(self) -> None:
        self._copy_value(self._clicked if self._clicked.isValid() else self._table.currentIndex())
