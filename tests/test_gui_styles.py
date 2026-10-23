from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QtMsgType, qInstallMessageHandler  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from cadmetrics.gui.control_panel import FlexibleDoubleSpinBox  # noqa: E402
from cadmetrics.gui.styles import application_stylesheet  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _stylesheet_warnings(app, stylesheet: str) -> list[str]:
    messages: list[str] = []

    def handler(mode: QtMsgType, context, message: str) -> None:
        messages.append(message)

    previous = qInstallMessageHandler(handler)
    try:
        # Style a local parent only: styling the whole QApplication re-polishes
        # every live widget from other tests and is slow.
        parent = QWidget()
        parent.setStyleSheet(stylesheet)
        layout = QVBoxLayout(parent)
        for widget in (QPushButton(), QCheckBox(), QTableWidget()):
            layout.addWidget(widget)
        parent.grab()
    finally:
        qInstallMessageHandler(previous)
    return [m for m in messages if "stylesheet" in m.lower() or "parse" in m.lower()]


def test_stylesheet_has_no_parse_warnings(app):
    assert not _stylesheet_warnings(app, application_stylesheet())


def test_parse_warning_check_detects_a_broken_stylesheet(app):
    assert _stylesheet_warnings(app, "QPushButton { color: ; ")


def test_disabled_primary_button_differs_from_enabled(app):
    parent = QWidget()
    parent.setStyleSheet(application_stylesheet())
    button = QPushButton("Run Sweep", parent)
    button.setObjectName("primaryButton")
    button.resize(120, 34)
    enabled = button.grab().toImage()
    button.setEnabled(False)
    disabled = button.grab().toImage()
    assert enabled.pixelColor(4, 17) != disabled.pixelColor(4, 17)


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
