from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QtMsgType, qInstallMessageHandler  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QPushButton,
    QTableWidget,
    QWidget,
)

from cadmetrics.gui.control_panel import FlexibleDoubleSpinBox  # noqa: E402
from cadmetrics.gui.styles import application_stylesheet  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_stylesheet_has_no_parse_warnings(app):
    messages: list[str] = []

    def handler(mode: QtMsgType, context, message: str) -> None:
        messages.append(message)

    previous = qInstallMessageHandler(handler)
    try:
        app.setStyleSheet(application_stylesheet())
        widgets = [QPushButton(), QCheckBox(), QTableWidget()]
        for widget in widgets:
            widget.grab()
    finally:
        qInstallMessageHandler(previous)
        app.setStyleSheet("")
    assert not [m for m in messages if "stylesheet" in m.lower()]


@pytest.mark.parametrize(
    "selector",
    [
        "QPushButton#primaryButton:disabled",
        "QPushButton#dangerButton:disabled",
        "QPushButton#primaryButton:pressed",
        "QTableView {",
        'QTableView[stale="true"]',
        "QCheckBox::indicator:checked:disabled",
        "QLabel#resultsStaleLabel",
        "QLabel#validationMessageLabel",
        "QToolButton#sectionToggle:checked",
    ],
)
def test_stylesheet_contains_selector(selector):
    assert selector in application_stylesheet()


def test_stylesheet_has_no_table_widget_selector():
    assert "QTableWidget" not in application_stylesheet()


def test_disabled_primary_button_differs_from_enabled(app):
    app.setStyleSheet(application_stylesheet())
    try:
        button = QPushButton("Run Sweep")
        button.setObjectName("primaryButton")
        button.resize(120, 34)
        enabled = button.grab().toImage()
        button.setEnabled(False)
        disabled = button.grab().toImage()
        assert enabled.pixelColor(4, 17) != disabled.pixelColor(4, 17)
    finally:
        app.setStyleSheet("")


def test_buttonless_spinbox_text_field_fills_the_box(app):
    # PySide6 6.12.0 shrank this field to 1px, hiding the value text.
    parent = QWidget()
    parent.setStyleSheet(application_stylesheet())
    field = FlexibleDoubleSpinBox(parent)
    field.resize(86, 34)
    parent.show()
    app.processEvents()
    try:
        assert field.lineEdit().width() >= field.width() - 20
    finally:
        parent.close()
