from __future__ import annotations

import tempfile
from pathlib import Path


def spinbox_arrow_image_urls() -> tuple[str, str]:
    asset_dir = Path(tempfile.gettempdir()) / "cadmetrics-gui-assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    up = asset_dir / "spin-up.svg"
    down = asset_dir / "spin-down.svg"
    up.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="8" viewBox="0 0 10 8">'
        '<path d="M5 1 L9 6 H1 Z" fill="#43505d"/></svg>',
        encoding="utf-8",
    )
    down.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="8" viewBox="0 0 10 8">'
        '<path d="M1 2 H9 L5 7 Z" fill="#43505d"/></svg>',
        encoding="utf-8",
    )
    return up.as_posix(), down.as_posix()


def with_spinbox_assets(stylesheet: str) -> str:
    up, down = spinbox_arrow_image_urls()
    return stylesheet.replace("__SPIN_UP_URL__", up).replace("__SPIN_DOWN_URL__", down)


APPLICATION_STYLESHEET = """
QWidget { color: #202832; font-size: 13px; }
QLineEdit, QComboBox, QDoubleSpinBox {
    min-height: 26px; border: 1px solid #c9d0d8; border-radius: 5px;
    padding: 2px 7px; background: #ffffff; selection-background-color: #2f78c4;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border-color: #2f78c4; }
QDoubleSpinBox { padding-right: 18px; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 18px; border-left: 1px solid #d5dbe2; background: #f8fafc;
}
QDoubleSpinBox::up-button {
    subcontrol-origin: border; subcontrol-position: top right;
    border-top-right-radius: 5px; height: 13px;
}
QDoubleSpinBox::down-button {
    subcontrol-origin: border; subcontrol-position: bottom right;
    border-bottom-right-radius: 5px; height: 13px;
}
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover { background: #eef3f8; }
QDoubleSpinBox::up-arrow { image: url("__SPIN_UP_URL__"); width: 10px; height: 8px; }
QDoubleSpinBox::down-arrow { image: url("__SPIN_DOWN_URL__"); width: 10px; height: 8px; }
QPushButton {
    min-height: 28px; border: 1px solid #b9c2cc; border-radius: 5px;
    padding: 4px 14px; background: #f8fafc; color: #1f2933; font-weight: 500;
}
QPushButton:hover { background: #eef3f8; border-color: #99a8b8; }
QPushButton:pressed { background: #e3eaf2; border-color: #8798aa; }
QPushButton:disabled { background: #edf0f3; border-color: #d5dbe1; color: #a3abb4; }
QPushButton#primaryButton { background: #256fb4; border-color: #1e609e; color: white; }
QPushButton#dangerButton { background: #fff7f5; border-color: #d8a59a; color: #9f3b2f; }
QCheckBox { min-height: 22px; spacing: 7px; }
QCheckBox::indicator {
    width: 14px; height: 14px; border: 1px solid #aab5c0;
    border-radius: 4px; background: #ffffff;
}
QCheckBox::indicator:checked { background: #2f78c4; border-color: #2f78c4; }
QCheckBox::indicator:disabled { background: #edf0f3; border-color: #d5dbe1; }
QGroupBox {
    border: 1px solid #d5d9de; border-radius: 6px; margin-top: 9px;
    padding: 10px 8px 8px 8px; background: #f9fafb;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; font-weight: 600; }
QToolButton#sectionToggle {
    border: 1px solid #d5d9de; border-radius: 6px; background: #f9fafb;
    font-weight: 600; padding: 7px 8px; text-align: left;
}
QToolButton#sectionToggle:hover { border-color: #b8c3cf; background: #ffffff; }
QProgressBar {
    min-height: 8px; max-height: 8px; border: 0; border-radius: 4px; background: #dce2e8;
}
QProgressBar::chunk { border-radius: 4px; background: #256fb4; }
QTextEdit { border: 1px solid #cfd6dd; border-radius: 5px; background: white; padding: 5px; }
QTableWidget {
    gridline-color: #e2e7ec; selection-background-color: #dcecff;
    alternate-background-color: #fafbfc; background: white; border: 0;
}
QHeaderView::section {
    min-height: 24px; padding: 4px 8px; border: 0;
    border-right: 1px solid #d9dee4; border-bottom: 1px solid #d9dee4;
    background: #f1f4f7; color: #43505d; font-weight: 600;
}
QStatusBar { border-top: 1px solid #d9dee4; background: #f7f9fb; }
QScrollArea { border: 0; background: #eef1f4; }
QWidget#resultToolbar { background: #f7f9fb; border-top: 1px solid #d9dee4; }
QLabel#resultCountLabel { color: #5f6872; font-weight: 500; }
"""


def application_stylesheet() -> str:
    return with_spinbox_assets(APPLICATION_STYLESHEET)
