from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6 import QtCore, QtGui, QtWidgets

from cadmetrics.gui.table_copy import TableCopyActions


@pytest.mark.parametrize("row_count", [0, 1])
def test_dismissed_menu_does_not_disable_later_copy_shortcuts(qtbot, row_count):
    table = QtWidgets.QTableView()
    qtbot.addWidget(table)
    model = QtGui.QStandardItemModel(row_count, 1, table)
    table.setModel(model)
    copied = []
    actions = TableCopyActions(
        table,
        copy_value=lambda _index: None,
        copy_row=lambda: copied.append("row"),
        copy_all=lambda: copied.append("all"),
    )
    table.show()
    table.setFocus()
    qtbot.waitUntil(table.hasFocus)
    # A reset or stale result can leave the visible table without a current row.
    table.setCurrentIndex(QtCore.QModelIndex())

    menu = actions.menu(QtCore.QModelIndex())
    assert not actions.copy_value.isEnabled()
    assert not actions.copy_row.isEnabled()
    assert actions.copy_all.isEnabled() == bool(row_count)
    # Dismissing the menu, without opening a native popup that would block the test.
    menu.aboutToHide.emit()

    model.setRowCount(1)
    table.setCurrentIndex(model.index(0, 0))
    assert actions.copy_row.isEnabled()
    assert actions.copy_all.isEnabled()
    qtbot.keyClick(table, QtCore.Qt.Key.Key_C, QtCore.Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClick(
        table,
        QtCore.Qt.Key.Key_C,
        QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier,
    )
    assert copied == ["row", "all"]
