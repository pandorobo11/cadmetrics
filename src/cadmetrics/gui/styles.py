from __future__ import annotations

import tempfile
from pathlib import Path


def spinbox_arrow_image_urls() -> tuple[str, str, str, str]:
    asset_dir = Path(tempfile.gettempdir()) / "cadmetrics-gui-assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    assets = (
        ("spin-up.svg", "M1 4 L4 1 L7 4 Z", "#657383"),
        ("spin-down.svg", "M1 1 L7 1 L4 4 Z", "#657383"),
        ("spin-up-disabled.svg", "M1 4 L4 1 L7 4 Z", "#a9b2bc"),
        ("spin-down-disabled.svg", "M1 1 L7 1 L4 4 Z", "#a9b2bc"),
    )
    urls: list[str] = []
    for filename, path, color in assets:
        asset = asset_dir / filename
        asset.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="5" '
            'viewBox="0 0 8 5">'
            f'<path d="{path}" fill="{color}"/></svg>',
            encoding="utf-8",
        )
        urls.append(asset.as_posix())
    return urls[0], urls[1], urls[2], urls[3]


def disclosure_arrow_image_urls() -> tuple[str, str]:
    asset_dir = Path(tempfile.gettempdir()) / "cadmetrics-gui-assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    assets = (
        ("disclosure-right.svg", "6", "10", "0 0 6 10", "M1 1 L5 5 L1 9 Z"),
        ("disclosure-down.svg", "10", "6", "0 0 10 6", "M1 1 L9 1 L5 5 Z"),
    )
    urls: list[str] = []
    for filename, width, height, view_box, path in assets:
        asset = asset_dir / filename
        asset.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="{view_box}"><path d="{path}" fill="#657383"/></svg>',
            encoding="utf-8",
        )
        urls.append(asset.as_posix())
    return urls[0], urls[1]


def with_spinbox_assets(stylesheet: str) -> str:
    up, down, up_disabled, down_disabled = spinbox_arrow_image_urls()
    replacements = {
        "__SPIN_UP_URL__": up,
        "__SPIN_DOWN_URL__": down,
        "__SPIN_UP_DISABLED_URL__": up_disabled,
        "__SPIN_DOWN_DISABLED_URL__": down_disabled,
    }
    for placeholder, url in replacements.items():
        stylesheet = stylesheet.replace(placeholder, url)
    return stylesheet


APPLICATION_STYLESHEET = """
QWidget { color: #202832; font-size: 13px; }
QWidget#controlPanel, QWidget#controlContent { background: #f3f6f9; }
QLineEdit, QComboBox, QDoubleSpinBox {
    min-height: 28px; border: 1px solid #bcc6d0; border-radius: 6px;
    padding: 2px 7px; background: #ffffff; selection-background-color: #2f78c4;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
    border: 2px solid #2f78c4; padding: 1px 6px;
}
QComboBox { padding-right: 29px; }
QComboBox::drop-down {
    subcontrol-origin: padding; subcontrol-position: top right;
    width: 27px; border: 0; border-left: 1px solid #c7d0da;
    border-top-right-radius: 5px; border-bottom-right-radius: 5px; background: #f7f9fb;
}
QComboBox::drop-down:hover { background: #eef3f8; }
QComboBox::drop-down:pressed { background: #e2eaf2; }
QComboBox::drop-down:disabled { background: #f7f9fb; }
QComboBox::down-arrow { image: url("__SPIN_DOWN_URL__"); width: 8px; height: 5px; }
QComboBox::down-arrow:disabled { image: url("__SPIN_DOWN_DISABLED_URL__"); }
QDoubleSpinBox { padding-right: 22px; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 21px; border: 0; border-left: 1px solid #c7d0da; background: #f7f9fb;
}
QDoubleSpinBox::up-button {
    subcontrol-origin: border; subcontrol-position: top right;
    border-top-right-radius: 5px; border-bottom: 1px solid #d8dfe6; height: 14px;
}
QDoubleSpinBox::down-button {
    subcontrol-origin: border; subcontrol-position: bottom right;
    border-bottom-right-radius: 5px; height: 14px;
}
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover { background: #eef3f8; }
QDoubleSpinBox::up-button:pressed, QDoubleSpinBox::down-button:pressed { background: #e2eaf2; }
QDoubleSpinBox::up-button:disabled, QDoubleSpinBox::down-button:disabled { background: #f7f9fb; }
QDoubleSpinBox::up-arrow { image: url("__SPIN_UP_URL__"); width: 8px; height: 5px; }
QDoubleSpinBox::down-arrow { image: url("__SPIN_DOWN_URL__"); width: 8px; height: 5px; }
QDoubleSpinBox::up-arrow:disabled { image: url("__SPIN_UP_DISABLED_URL__"); }
QDoubleSpinBox::down-arrow:disabled { image: url("__SPIN_DOWN_DISABLED_URL__"); }
QPushButton {
    min-height: 30px; border: 1px solid #aeb9c5; border-radius: 6px;
    padding: 4px 14px; background: #f8fafc; color: #1f2933; font-weight: 500;
}
QPushButton:hover { background: #eef3f8; border-color: #99a8b8; }
QPushButton:pressed { background: #e3eaf2; border-color: #8798aa; }
QPushButton:focus, QToolButton:focus { border: 2px solid #2f78c4; }
QPushButton:disabled { background: #e9edf1; border-color: #cdd4dc; color: #77818c; }
QPushButton#primaryButton { background: #256fb4; border-color: #1e609e; color: white; }
QPushButton#primaryButton:hover { background: #1f65a5; }
QPushButton#dangerButton { background: #fff7f5; border-color: #d8a59a; color: #9f3b2f; }
QCheckBox { min-height: 28px; spacing: 8px; }
QCheckBox:focus { color: #165f9f; }
QCheckBox::indicator {
    width: 16px; height: 16px; border: 1px solid #98a6b4;
    border-radius: 4px; background: #ffffff;
}
QCheckBox::indicator:checked { background: #2f78c4; border-color: #2f78c4; }
QCheckBox::indicator:disabled { background: #edf0f3; border-color: #d5dbe1; }
QGroupBox {
    border: 0; border-radius: 8px; margin-top: 10px;
    padding: 11px 8px 8px 8px; background: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 8px; padding: 0 4px;
    font-size: 14px; font-weight: 600; color: #17212b;
}
QGroupBox#sectionContent {
    margin-top: 0; padding: 0; border: 0; border-radius: 8px; background: #ffffff;
}
QToolButton#sectionToggle {
    min-height: 32px; border: 0; border-radius: 7px; background: #ffffff;
    font-weight: 600; padding: 5px 10px; text-align: left;
}
QToolButton#sectionToggle:hover { background: #eaf0f6; }
QToolButton#sectionToggle:checked { background: #eaf0f6; }
QProgressBar {
    min-height: 8px; max-height: 8px; border: 0; border-radius: 4px; background: #dce2e8;
}
QProgressBar::chunk { border-radius: 4px; background: #256fb4; }
QTextEdit { border: 1px solid #c7d0d9; border-radius: 6px; background: white; padding: 7px; }
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
QScrollArea { border: 0; background: #f3f6f9; }
QWidget#actionBar {
    background: #ffffff; border-top: 1px solid #d7dee6;
}
QLabel#modelSummaryLabel { color: #53606d; font-size: 12px; }
QLabel#operationLabel { color: #165f9f; font-weight: 600; }
QLabel#caseCountLabel { color: #53606d; font-size: 12px; font-weight: 600; }
QLabel#caseCountLabel[invalid="true"] { color: #a23b32; }
QLabel#dirtyStatusLabel {
    color: #925c12; background: #fff4d8; border-radius: 5px; padding: 5px 7px;
}
QWidget#resultToolbar { background: #f7f9fb; border-top: 1px solid #d9dee4; }
QLabel#resultCountLabel { color: #5f6872; font-weight: 500; }
QLabel#emptyStateTitle { color: #344150; font-size: 16px; font-weight: 600; }
QLabel#emptyStateMessage { color: #6b7682; font-size: 13px; }
"""


def application_stylesheet() -> str:
    return with_spinbox_assets(APPLICATION_STYLESHEET)
