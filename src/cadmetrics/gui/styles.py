from __future__ import annotations

import tempfile
from pathlib import Path


def spinbox_arrow_image_urls() -> tuple[str, str, str, str]:
    asset_dir = Path(tempfile.gettempdir()) / "cadmetrics-gui-assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    up, down = "M1.5 5 L5 1.5 L8.5 5", "M1.5 1 L5 4.5 L8.5 1"
    assets = (
        ("chevron-up.svg", up, "#4f5d6b"),
        ("chevron-down.svg", down, "#4f5d6b"),
        ("chevron-up-disabled.svg", up, "#b3bcc6"),
        ("chevron-down-disabled.svg", down, "#b3bcc6"),
    )
    urls: list[str] = []
    for filename, path, color in assets:
        asset = asset_dir / filename
        asset.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6" '
            'viewBox="0 0 10 6">'
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.5" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>',
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


def checkbox_check_image_urls() -> tuple[str, str]:
    asset_dir = Path(tempfile.gettempdir()) / "cadmetrics-gui-assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    assets = (
        ("check-on.svg", "#ffffff"),
        ("check-on-disabled.svg", "#7d8895"),
    )
    urls: list[str] = []
    for filename, color in assets:
        asset = asset_dir / filename
        asset.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
            'viewBox="0 0 16 16"><path d="M4 8.5 L7 11.5 L12 5" fill="none" '
            f'stroke="{color}" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round"/></svg>',
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
    check_on, check_on_disabled = checkbox_check_image_urls()
    replacements["__CHECK_ON_URL__"] = check_on
    replacements["__CHECK_ON_DISABLED_URL__"] = check_on_disabled
    for placeholder, url in replacements.items():
        stylesheet = stylesheet.replace(placeholder, url)
    return stylesheet


APPLICATION_STYLESHEET = """
QWidget { color: #202832; font-size: 13px; font-weight: 400; }
QWidget#controlPanel, QWidget#controlContent { background: #f3f6f9; }
/* Controls share one 34px height: min-height + vertical padding + 1px borders. */
QLineEdit, QComboBox, QDoubleSpinBox {
    min-height: 28px; max-height: 28px; border: 1px solid #bcc6d0; border-radius: 6px;
    padding: 2px 7px; background: #ffffff; selection-background-color: #2f78c4;
}
QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover { border-color: #93a2b2; }
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
    border: 2px solid #2f78c4; padding: 1px 6px;
}
QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled {
    background: #f4f6f8; border-color: #d5dbe1; color: #7b8590;
}
QComboBox { padding-right: 26px; }
QComboBox::drop-down {
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 24px; border: 0; background: transparent;
}
QComboBox::down-arrow { image: url("__SPIN_DOWN_URL__"); width: 10px; height: 6px; }
QComboBox::down-arrow:disabled { image: url("__SPIN_DOWN_DISABLED_URL__"); }
QComboBox QAbstractItemView {
    border: 1px solid #c7d0da; border-radius: 6px; padding: 4px; background: #ffffff;
    outline: 0; selection-background-color: #e3eefb; selection-color: #10263d;
}
QComboBox QAbstractItemView::item { min-height: 26px; padding: 0 8px; border-radius: 4px; }
QComboBox QAbstractItemView::item:hover { background: #eef3f8; }
QComboBox QAbstractItemView::item:selected { background: #dcebfb; color: #10263d; }
QDoubleSpinBox { padding-right: 7px; }
QPushButton {
    min-height: 24px; border: 1px solid #bcc6d0; border-radius: 6px;
    padding: 4px 14px; background: #f8fafc; color: #1f2933; font-weight: 500;
}
QPushButton:hover { background: #eef3f8; border-color: #93a2b2; }
QPushButton:pressed { background: #e3eaf2; border-color: #8798aa; }
/* Thicker focus borders give up the same amount of padding so sizes stay fixed. */
QPushButton:focus { border: 2px solid #2f78c4; padding: 3px 13px; }
QToolButton:focus { border: 2px solid #2f78c4; }
QPushButton:disabled { background: #e9edf1; border-color: #cdd4dc; color: #66707b; }
QPushButton#primaryButton { background: #256fb4; border-color: #1e609e; color: white; }
QPushButton#primaryButton:hover { background: #1f65a5; }
QPushButton#primaryButton:pressed { background: #184f85; border-color: #143f6a; }
QPushButton#primaryButton:focus { border: 2px solid #0f3d6b; padding: 3px 13px; }
QPushButton#primaryButton:disabled {
    background: #e9edf1; border-color: #cdd4dc; color: #66707b;
}
QPushButton#dangerButton { background: #fff7f5; border-color: #d8a59a; color: #9f3b2f; }
QPushButton#dangerButton:hover { background: #ffece8; border-color: #c98a7d; }
QPushButton#dangerButton:pressed { background: #fbdcd5; }
QPushButton#dangerButton:disabled {
    background: #e9edf1; border-color: #cdd4dc; color: #66707b;
}
QCheckBox { min-height: 28px; spacing: 8px; }
QCheckBox:focus { color: #165f9f; }
QCheckBox::indicator {
    width: 16px; height: 16px; border: 1px solid #98a6b4;
    border-radius: 4px; background: #ffffff;
}
QCheckBox::indicator:checked {
    background: #2f78c4; border-color: #2f78c4; image: url("__CHECK_ON_URL__");
}
QCheckBox::indicator:disabled { background: #edf0f3; border-color: #d5dbe1; }
QCheckBox::indicator:checked:disabled {
    background: #dde3ea; border-color: #c3ccd6; image: url("__CHECK_ON_DISABLED_URL__");
}
QGroupBox {
    border: 0; border-radius: 8px; margin-top: 0;
    padding: 34px 0 0 0; background: #ffffff; font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: padding; subcontrol-position: top left; left: 24px; top: 10px;
    padding: 0; font-size: 13px; font-weight: 600; color: #17212b;
}
QGroupBox#sectionContent {
    margin-top: 0; padding: 0; border: 0; background: #ffffff;
    border-top-left-radius: 0; border-top-right-radius: 0;
    border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;
}
QToolButton#sectionToggle {
    min-height: 32px; border: 0; border-radius: 7px; background: #ffffff;
    font-weight: 600; padding: 5px 12px; text-align: left;
}
QToolButton#sectionToggle:hover { background: #eaf0f6; }
QToolButton#sectionToggle:checked {
    background: #ffffff; border-bottom: 1px solid #e6ebf0;
    border-bottom-left-radius: 0; border-bottom-right-radius: 0;
}
QToolButton#sectionToggle:checked:hover { background: #f3f7fa; }
QScrollArea#componentList {
    border: 1px solid #dbe1e7; border-radius: 6px; background: #ffffff;
}
QWidget#componentListContent { background: #ffffff; }
/* One sub-heading style: column headings, groups, and section sub-groups. */
QLabel#subheadingLabel { color: #5f6b78; font-size: 12px; font-weight: 600; }
QProgressBar {
    min-height: 8px; max-height: 8px; border: 0; border-radius: 4px; background: #dce2e8;
}
QProgressBar::chunk { border-radius: 4px; background: #256fb4; }
QTextEdit { border: 1px solid #c7d0d9; border-radius: 6px; background: white; padding: 7px; }
QTableView {
    gridline-color: #e2e7ec; selection-background-color: #bfdcfa;
    selection-color: #10263d; alternate-background-color: #f6f8fa;
    background: white; border: 0;
}
QTableView[stale="true"] { color: #8a949f; }
QTableView[stale="true"]::item:selected { color: #5b6672; }
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
QLabel#caseCountLabel { color: #5f6b78; font-size: 12px; font-weight: 600; }
QLabel#caseCountLabel[invalid="true"] { color: #a23b32; }
QLabel#dirtyStatusLabel {
    color: #925c12; background: #fff4d8; border-radius: 5px; padding: 5px 7px;
}
QLabel#resultsStaleLabel {
    color: #925c12; background: #fff4d8; border-radius: 5px; padding: 5px 7px;
}
QLabel#validationMessageLabel { color: #a23b32; font-size: 12px; }
QLabel#fieldHint { color: #5f6b78; font-size: 12px; }
QWidget#viewerToolbar { background: #f7f9fb; border-bottom: 1px solid #d9dee4; }
QLabel#viewerToolbarLabel { color: #4a5663; font-size: 12px; font-weight: 600; padding-right: 4px; }
QToolButton#viewButton {
    min-height: 24px; padding: 1px 6px; border: 1px solid #c7d0da;
    border-radius: 5px; background: #ffffff; color: #1f2933; font-size: 12px;
}
QToolButton#viewButton:hover { background: #eef3f8; border-color: #99a8b8; }
QToolButton#viewButton:pressed { background: #e2eaf2; }
QToolButton#viewButton:disabled { background: #f1f4f7; border-color: #dbe1e7; color: #66707b; }
QPushButton#viewerSaveButton { min-height: 24px; padding: 1px 10px; font-size: 12px; }
QWidget#resultToolbar { background: #f7f9fb; border-top: 1px solid #d9dee4; }
QLabel#resultCountLabel { color: #5f6872; font-weight: 500; }
QLabel#emptyStateTitle { color: #344150; font-size: 16px; font-weight: 600; }
QLabel#emptyStateMessage { color: #58636f; font-size: 13px; }
"""


def application_stylesheet() -> str:
    return with_spinbox_assets(APPLICATION_STYLESHEET)
