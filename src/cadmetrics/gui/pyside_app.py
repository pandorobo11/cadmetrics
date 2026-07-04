from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from threading import Event
from typing import Any

import numpy as np

from cadmetrics.api import inspect_model
from cadmetrics.coordinates import AXIS_CHOICES
from cadmetrics.gui.export import write_rows_csv
from cadmetrics.gui.jobs import CalculationRequest, run_calculation
from cadmetrics.orientation import Orientation, parse_vector, projection_direction_for_orientation
from cadmetrics.projection import projection_basis
from cadmetrics.types import MeasurementRow, ModelData

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:  # pragma: no cover - exercised by entry point in environments without GUI extra
    QtCore = None
    QtWidgets = None

UNIT_OPTIONS = ["auto", "m", "mm", "cm", "in", "ft"]
OUTPUT_UNIT_OPTIONS = ["m", "mm", "cm", "in", "ft"]
TABLE_COLUMNS = [
    "file",
    "input_unit",
    "output_unit",
    "roll_deg",
    "pitch_deg",
    "alpha_deg",
    "beta_deg",
    "direction_x",
    "direction_y",
    "direction_z",
    "x_min",
    "x_max",
    "y_min",
    "y_max",
    "z_min",
    "z_max",
    "surface_area",
    "volume",
    "projected_area",
    "centroid_u",
    "centroid_v",
    "centroid_x",
    "centroid_y",
    "centroid_z",
    "is_watertight",
    "mesh_deflection",
    "angular_deflection",
    "method",
    "elapsed_sec",
    "cadmetrics_version",
    "cadmetrics_hash",
    "warnings",
]


class MissingGuiDependency(RuntimeError):
    pass


if QtCore is not None:

    class CalculationWorker(QtCore.QObject):
        finished = QtCore.Signal(list)
        failed = QtCore.Signal(str)
        progress = QtCore.Signal(int, int, str)
        cancelled = QtCore.Signal()

        def __init__(self, request: CalculationRequest) -> None:
            super().__init__()
            self._request = request
            self._cancel = Event()

        @QtCore.Slot()
        def run(self) -> None:
            try:
                rows = run_calculation(self._request, progress_callback=self._on_progress)
            except _CancelledCalculation:
                self.cancelled.emit()
                return
            except Exception as exc:
                self.failed.emit(str(exc))
                return
            self.finished.emit(rows)

        def cancel(self) -> None:
            self._cancel.set()

        def _on_progress(self, index: int, total: int, description: str) -> None:
            if self._cancel.is_set():
                raise _CancelledCalculation
            self.progress.emit(index, total, description)


if QtWidgets is not None:

    class FlexibleDoubleSpinBox(QtWidgets.QDoubleSpinBox):
        def textFromValue(self, value: float) -> str:  # noqa: N802
            text = f"{value:.{self.decimals()}f}".rstrip("0").rstrip(".")
            if "." not in text:
                text = f"{text}.0"
            return text

else:
    CalculationWorker = object  # type: ignore[misc,assignment]
    FlexibleDoubleSpinBox = object  # type: ignore[misc,assignment]


class _CancelledCalculation(Exception):
    pass


def _spinbox_arrow_image_urls() -> tuple[str, str]:
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


def main() -> None:
    if QtWidgets is None:
        raise MissingGuiDependency(
            "PySide6 GUI dependencies are not installed. Run: uv sync --extra gui"
        )
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.resize(1320, 820)
    window.show()
    raise SystemExit(app.exec())


if QtWidgets is not None:

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("cadmetrics")
            self._model: ModelData | None = None
            self._rows: list[MeasurementRow] = []
            self._thread: QtCore.QThread | None = None
            self._worker: CalculationWorker | None = None
            self._plotter: Any | None = None
            self._vector_actor: Any | None = None
            self._mesh_actor: Any | None = None
            self._feature_edges_actor: Any | None = None
            self._mesh_polydata: Any | None = None
            self._centroid_actor: Any | None = None
            self._overlay_actor: Any | None = None
            self._overlay_row: MeasurementRow | None = None
            self._component_checkboxes: list[QtWidgets.QCheckBox] = []
            self._component_filter_path: Path | None = None

            self._build_ui()
            self._set_running(False)

        def _build_ui(self) -> None:
            root = QtWidgets.QSplitter()
            root.setOrientation(QtCore.Qt.Orientation.Horizontal)
            self.setCentralWidget(root)
            spin_up_url, spin_down_url = _spinbox_arrow_image_urls()

            self.setStyleSheet(
                """
                QWidget {
                    color: #202832;
                    font-size: 13px;
                }
                QLineEdit, QComboBox, QDoubleSpinBox {
                    min-height: 26px;
                    border: 1px solid #c9d0d8;
                    border-radius: 5px;
                    padding: 2px 7px;
                    background: #ffffff;
                    selection-background-color: #2f78c4;
                }
                QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
                    border-color: #2f78c4;
                }
                QDoubleSpinBox {
                    padding-right: 18px;
                }
                QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                    width: 18px;
                    border-left: 1px solid #d5dbe2;
                    background: #f8fafc;
                }
                QDoubleSpinBox::up-button {
                    subcontrol-origin: border;
                    subcontrol-position: top right;
                    border-top-right-radius: 5px;
                    height: 13px;
                }
                QDoubleSpinBox::down-button {
                    subcontrol-origin: border;
                    subcontrol-position: bottom right;
                    border-bottom-right-radius: 5px;
                    height: 13px;
                }
                QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
                    background: #eef3f8;
                }
                QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {
                    width: 10px;
                    height: 8px;
                }
                QDoubleSpinBox::up-arrow {
                    image: url("__SPIN_UP_URL__");
                }
                QDoubleSpinBox::down-arrow {
                    image: url("__SPIN_DOWN_URL__");
                }
                QPushButton {
                    min-height: 28px;
                    border: 1px solid #b9c2cc;
                    border-radius: 5px;
                    padding: 4px 14px;
                    background: #f8fafc;
                    color: #1f2933;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background: #eef3f8;
                    border-color: #99a8b8;
                }
                QPushButton:pressed {
                    background: #e3eaf2;
                    border-color: #8798aa;
                }
                QPushButton:disabled {
                    background: #edf0f3;
                    border-color: #d5dbe1;
                    color: #a3abb4;
                }
                QPushButton#primaryButton {
                    background: #256fb4;
                    border-color: #1e609e;
                    color: #ffffff;
                }
                QPushButton#primaryButton:hover {
                    background: #1f64a5;
                    border-color: #195487;
                }
                QPushButton#primaryButton:pressed {
                    background: #184f83;
                    border-color: #143f68;
                }
                QPushButton#primaryButton:disabled {
                    background: #b9cfe4;
                    border-color: #b9cfe4;
                    color: #eef5fb;
                }
                QPushButton#dangerButton {
                    background: #fff7f5;
                    border-color: #d8a59a;
                    color: #9f3b2f;
                }
                QPushButton#dangerButton:hover {
                    background: #ffece8;
                    border-color: #c98173;
                }
                QPushButton#dangerButton:pressed {
                    background: #ffdcd6;
                    border-color: #b56f63;
                }
                QCheckBox {
                    min-height: 22px;
                    spacing: 7px;
                }
                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                    border: 1px solid #aab5c0;
                    border-radius: 4px;
                    background: #ffffff;
                }
                QCheckBox::indicator:checked {
                    background: #2f78c4;
                    border-color: #2f78c4;
                }
                QCheckBox::indicator:disabled {
                    background: #edf0f3;
                    border-color: #d5dbe1;
                }
                QGroupBox {
                    border: 1px solid #d5d9de;
                    border-radius: 6px;
                    margin-top: 9px;
                    padding: 10px 8px 8px 8px;
                    background: #f9fafb;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 8px;
                    padding: 0 4px;
                    color: #202832;
                    font-weight: 600;
                }
                QToolButton#sectionToggle {
                    border: 1px solid #d5d9de;
                    border-radius: 6px;
                    background: #f9fafb;
                    color: #202832;
                    font-weight: 600;
                    padding: 7px 8px;
                    text-align: left;
                }
                QToolButton#sectionToggle:hover {
                    border-color: #b8c3cf;
                    background: #ffffff;
                }
                QProgressBar {
                    min-height: 8px;
                    max-height: 8px;
                    border: 0;
                    border-radius: 4px;
                    background: #dce2e8;
                    text-align: center;
                }
                QProgressBar::chunk {
                    border-radius: 4px;
                    background: #256fb4;
                }
                QTextEdit {
                    border: 1px solid #cfd6dd;
                    border-radius: 5px;
                    background: #ffffff;
                    padding: 5px;
                }
                QTableWidget {
                    gridline-color: #e2e7ec;
                    selection-background-color: #dcecff;
                    selection-color: #202832;
                    alternate-background-color: #fafbfc;
                    background: #ffffff;
                    border: 0;
                }
                QHeaderView::section {
                    min-height: 24px;
                    padding: 4px 8px;
                    border: 0;
                    border-right: 1px solid #d9dee4;
                    border-bottom: 1px solid #d9dee4;
                    background: #f1f4f7;
                    color: #43505d;
                    font-weight: 600;
                }
                QStatusBar {
                    border-top: 1px solid #d9dee4;
                    background: #f7f9fb;
                }
                QScrollArea {
                    border: 0;
                    background: #eef1f4;
                }
                QWidget#resultToolbar {
                    background: #f7f9fb;
                    border-top: 1px solid #d9dee4;
                }
                QLabel#resultCountLabel {
                    color: #5f6872;
                    font-weight: 500;
                }
                """
                .replace("__SPIN_UP_URL__", spin_up_url)
                .replace("__SPIN_DOWN_URL__", spin_down_url)
            )

            controls = QtWidgets.QScrollArea()
            controls.setMinimumWidth(430)
            controls.setMaximumWidth(540)
            controls.setWidgetResizable(True)
            controls.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

            controls_content = QtWidgets.QWidget()
            controls.setWidget(controls_content)
            panel_layout = QtWidgets.QVBoxLayout(controls_content)
            panel_layout.setContentsMargins(12, 4, 12, 8)
            panel_layout.setSpacing(5)

            setup_layout = self._make_section(panel_layout, "Setup")
            self.file_edit = QtWidgets.QLineEdit()
            self.file_edit.setPlaceholderText("STL or STEP file")
            browse = QtWidgets.QPushButton("Browse")
            browse.setObjectName("secondaryButton")
            browse.clicked.connect(self._browse_file)
            file_row = QtWidgets.QHBoxLayout()
            file_row.setContentsMargins(0, 0, 0, 0)
            file_row.setSpacing(8)
            file_row.addWidget(self.file_edit)
            file_row.addWidget(browse)
            setup_layout.addRow("File", file_row)

            self.input_unit = QtWidgets.QComboBox()
            self.input_unit.addItems(UNIT_OPTIONS)
            setup_layout.addRow("Input unit", self.input_unit)

            self.output_unit = QtWidgets.QComboBox()
            self.output_unit.addItems(OUTPUT_UNIT_OPTIONS)
            setup_layout.addRow("Output unit", self.output_unit)

            self.attitude_box = QtWidgets.QGroupBox("Attitude")
            attitude_layout = QtWidgets.QVBoxLayout(self.attitude_box)
            attitude_layout.setContentsMargins(8, 6, 8, 8)
            attitude_layout.setSpacing(5)
            panel_layout.addWidget(self.attitude_box)

            self.attitude_mode = QtWidgets.QComboBox()
            self.attitude_mode.addItem("Alpha / Beta", "alpha_beta")
            self.attitude_mode.addItem("Roll / Pitch", "roll_pitch")
            self.attitude_mode.addItem("Unit vector", "vector")
            self.attitude_mode.currentIndexChanged.connect(self._sync_attitude_controls)
            self.attitude_mode.currentIndexChanged.connect(self._update_projection_vector)
            attitude_layout.addWidget(self.attitude_mode)

            (
                self.alpha_beta_group,
                (self.alpha_start, self.alpha_end, self.alpha_step),
                (self.beta_start, self.beta_end, self.beta_step),
            ) = self._make_sweep_grid("Alpha", "Beta")
            (
                self.roll_pitch_group,
                (self.roll_start, self.roll_end, self.roll_step),
                (self.pitch_start, self.pitch_end, self.pitch_step),
            ) = self._make_sweep_grid("Roll", "Pitch")
            (
                self.vector_group,
                self.vector_x,
                self.vector_y,
                self.vector_z,
            ) = self._make_vector_inputs()
            attitude_layout.addWidget(self.alpha_beta_group)
            attitude_layout.addWidget(self.roll_pitch_group)
            attitude_layout.addWidget(self.vector_group)

            for field in (
                self.roll_start,
                self.roll_end,
                self.roll_step,
                self.alpha_start,
                self.alpha_end,
                self.alpha_step,
                self.beta_start,
                self.beta_end,
                self.beta_step,
                self.pitch_start,
                self.pitch_end,
                self.pitch_step,
                self.vector_x,
                self.vector_y,
                self.vector_z,
            ):
                field.valueChanged.connect(self._update_projection_vector)

            run_layout = QtWidgets.QHBoxLayout()
            run_layout.setContentsMargins(0, 0, 0, 0)
            run_layout.setSpacing(8)
            self.run_button = QtWidgets.QPushButton("Run Sweep")
            self.run_button.setObjectName("primaryButton")
            self.run_button.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            self.run_button.clicked.connect(self._start_calculation)
            self.cancel_button = QtWidgets.QPushButton("Cancel")
            self.cancel_button.setObjectName("dangerButton")
            self.cancel_button.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            self.cancel_button.clicked.connect(self._cancel_calculation)
            run_layout.addWidget(self.run_button)
            run_layout.addWidget(self.cancel_button)
            panel_layout.addLayout(run_layout)

            display_box = QtWidgets.QGroupBox("Shape Display")
            display_layout = QtWidgets.QGridLayout(display_box)
            display_layout.setContentsMargins(8, 6, 8, 6)
            display_layout.setHorizontalSpacing(12)
            display_layout.setVerticalSpacing(4)
            self.transparent_shape = QtWidgets.QCheckBox("Transparent")
            self.transparent_shape.setChecked(False)
            self.mesh_edges = QtWidgets.QCheckBox("Mesh edges")
            self.mesh_edges.setChecked(False)
            self.feature_edges = QtWidgets.QCheckBox("Feature edges")
            self.feature_edges.setChecked(True)
            self.show_overlay = QtWidgets.QCheckBox("Overlay")
            self.show_overlay.setChecked(True)
            self.save_image_button = QtWidgets.QPushButton("Save Image")
            self.save_image_button.setObjectName("secondaryButton")
            self.transparent_shape.toggled.connect(self._apply_display_options)
            self.mesh_edges.toggled.connect(self._apply_display_options)
            self.feature_edges.toggled.connect(self._apply_display_options)
            self.show_overlay.toggled.connect(self._update_overlay)
            self.save_image_button.clicked.connect(self._save_view_image)
            display_layout.addWidget(self.transparent_shape, 0, 0)
            display_layout.addWidget(self.mesh_edges, 0, 1)
            display_layout.addWidget(self.feature_edges, 1, 0)
            display_layout.addWidget(self.show_overlay, 1, 1)
            display_layout.addWidget(self.save_image_button, 2, 0, 1, 2)
            panel_layout.addWidget(display_box)

            advanced_layout = self._make_collapsible_section(panel_layout, "Advanced")

            self._add_advanced_heading(advanced_layout, "Geometry")
            self.axis_x = self._axis_combo("x")
            self.axis_y = self._axis_combo("y")
            self.axis_z = self._axis_combo("z")
            axis_widget = QtWidgets.QWidget()
            axis_layout = QtWidgets.QHBoxLayout(axis_widget)
            axis_layout.setContentsMargins(0, 0, 0, 0)
            axis_layout.setSpacing(6)
            axis_layout.addWidget(QtWidgets.QLabel("X"))
            axis_layout.addWidget(self.axis_x, 1)
            axis_layout.addWidget(QtWidgets.QLabel("Y"))
            axis_layout.addWidget(self.axis_y, 1)
            axis_layout.addWidget(QtWidgets.QLabel("Z"))
            axis_layout.addWidget(self.axis_z, 1)
            advanced_layout.addRow("Axis map", axis_widget)

            self._add_advanced_heading(advanced_layout, "Components")
            component_widget = QtWidgets.QWidget()
            component_layout = QtWidgets.QVBoxLayout(component_widget)
            component_layout.setContentsMargins(0, 0, 0, 0)
            component_layout.setSpacing(6)
            self.component_summary = QtWidgets.QLabel("Load a multi-solid STEP file.")
            self.component_summary.setStyleSheet("color: #5f6872;")
            component_layout.addWidget(self.component_summary)
            self.component_list_widget = QtWidgets.QWidget()
            self.component_list_layout = QtWidgets.QVBoxLayout(self.component_list_widget)
            self.component_list_layout.setContentsMargins(0, 0, 0, 0)
            self.component_list_layout.setSpacing(2)
            component_scroll = QtWidgets.QScrollArea()
            component_scroll.setWidgetResizable(True)
            component_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            component_scroll.setMaximumHeight(105)
            component_scroll.setWidget(self.component_list_widget)
            component_layout.addWidget(component_scroll)
            component_button_row = QtWidgets.QHBoxLayout()
            component_button_row.setContentsMargins(0, 0, 0, 0)
            component_button_row.setSpacing(6)
            self.component_all_button = QtWidgets.QPushButton("All")
            self.component_none_button = QtWidgets.QPushButton("None")
            for button in (self.component_all_button, self.component_none_button):
                button.setObjectName("secondaryButton")
            self.component_all_button.clicked.connect(lambda: self._set_all_components(True))
            self.component_none_button.clicked.connect(lambda: self._set_all_components(False))
            component_button_row.addWidget(self.component_all_button)
            component_button_row.addWidget(self.component_none_button)
            component_button_row.addStretch(1)
            component_layout.addLayout(component_button_row)
            advanced_layout.addRow("Components", component_widget)
            self._sync_component_controls(False)

            self._add_advanced_heading(advanced_layout, "Metrics")
            self.step_metrics = QtWidgets.QComboBox()
            self.step_metrics.addItem("B-Rep (default)", "brep")
            self.step_metrics.addItem("Mesh", "mesh")
            advanced_layout.addRow("STEP metrics", self.step_metrics)

            self._add_advanced_heading(advanced_layout, "Tessellation")
            self.mesh_deflection = FlexibleDoubleSpinBox()
            self.mesh_deflection.setRange(1.0e-8, 1.0)
            self.mesh_deflection.setDecimals(8)
            self.mesh_deflection.setSingleStep(1.0e-4)
            self.mesh_deflection.setValue(1.0e-3)
            self.mesh_deflection_auto = QtWidgets.QCheckBox("Auto")
            self.mesh_deflection_auto.setChecked(True)
            self.mesh_deflection_auto.toggled.connect(self._sync_mesh_deflection_controls)
            mesh_deflection_row = QtWidgets.QHBoxLayout()
            mesh_deflection_row.setContentsMargins(0, 0, 0, 0)
            mesh_deflection_row.setSpacing(8)
            mesh_deflection_row.addWidget(self.mesh_deflection)
            mesh_deflection_row.addWidget(self.mesh_deflection_auto)
            advanced_layout.addRow("Mesh deflection", mesh_deflection_row)

            self.angular_deflection = FlexibleDoubleSpinBox()
            self.angular_deflection.setRange(1.0e-6, 1.0)
            self.angular_deflection.setDecimals(6)
            self.angular_deflection.setSingleStep(0.1)
            self.angular_deflection.setValue(0.1)
            advanced_layout.addRow("Angular deflection", self.angular_deflection)

            self.apply_advanced_button = QtWidgets.QPushButton("Apply Settings")
            self.apply_advanced_button.setObjectName("secondaryButton")
            self.apply_advanced_button.clicked.connect(self._apply_advanced_settings)
            advanced_layout.addRow(self.apply_advanced_button)

            model_box = QtWidgets.QGroupBox("Model Info")
            model_box.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
            model_layout = QtWidgets.QVBoxLayout(model_box)
            model_layout.setContentsMargins(8, 6, 8, 8)
            self.model_info = QtWidgets.QTextEdit()
            self.model_info.setReadOnly(True)
            self.model_info.setMinimumHeight(130)
            self.model_info.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
            model_layout.addWidget(self.model_info)
            panel_layout.addWidget(model_box)

            self.status = QtWidgets.QLabel("Ready")
            self.status.setWordWrap(False)
            self.progress = QtWidgets.QProgressBar()
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self.progress.setFixedWidth(180)
            self.progress.setTextVisible(False)
            status_bar = QtWidgets.QStatusBar()
            status_bar.addWidget(self.status, 1)
            status_bar.addPermanentWidget(self.progress)
            self.setStatusBar(status_bar)

            right = QtWidgets.QSplitter()
            right.setOrientation(QtCore.Qt.Orientation.Vertical)

            self.viewer = self._create_viewer()
            right.addWidget(self.viewer)

            self.table = QtWidgets.QTableWidget(0, len(TABLE_COLUMNS))
            self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)
            self.table.horizontalHeader().setStretchLastSection(True)
            self.table.setAlternatingRowColors(True)
            self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
            self.table.verticalHeader().setVisible(False)
            self.table.verticalHeader().setDefaultSectionSize(24)
            self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
            table_panel = QtWidgets.QWidget()
            table_layout = QtWidgets.QVBoxLayout(table_panel)
            table_layout.setContentsMargins(0, 0, 0, 0)
            table_layout.setSpacing(0)
            result_toolbar = QtWidgets.QWidget()
            result_toolbar.setObjectName("resultToolbar")
            result_layout = QtWidgets.QHBoxLayout(result_toolbar)
            result_layout.setContentsMargins(10, 6, 10, 6)
            self.result_count = QtWidgets.QLabel("Rows: 0")
            self.result_count.setObjectName("resultCountLabel")
            self.save_button = QtWidgets.QPushButton("Save CSV")
            self.save_button.setObjectName("secondaryButton")
            self.save_button.clicked.connect(self._save_csv)
            result_layout.addWidget(self.result_count)
            result_layout.addStretch(1)
            result_layout.addWidget(self.save_button)
            table_layout.addWidget(result_toolbar)
            table_layout.addWidget(self.table)
            right.addWidget(table_panel)
            right.setSizes([560, 260])

            root.addWidget(controls)
            root.addWidget(right)
            root.setSizes([440, 880])
            self._sync_attitude_controls()
            self._sync_mesh_deflection_controls()

        def _make_section(
            self,
            parent_layout: QtWidgets.QVBoxLayout,
            title: str,
        ) -> QtWidgets.QFormLayout:
            box = QtWidgets.QGroupBox(title)
            layout = QtWidgets.QFormLayout(box)
            layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.DontWrapRows)
            layout.setVerticalSpacing(6)
            layout.setHorizontalSpacing(10)
            layout.setContentsMargins(8, 6, 8, 7)
            parent_layout.addWidget(box)
            return layout

        def _make_collapsible_section(
            self,
            parent_layout: QtWidgets.QVBoxLayout,
            title: str,
        ) -> QtWidgets.QFormLayout:
            toggle = QtWidgets.QToolButton()
            toggle.setObjectName("sectionToggle")
            toggle.setText(title)
            toggle.setCheckable(True)
            toggle.setChecked(False)
            toggle.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            toggle.setArrowType(QtCore.Qt.ArrowType.RightArrow)

            content = QtWidgets.QGroupBox()
            layout = QtWidgets.QFormLayout(content)
            layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            layout.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.DontWrapRows)
            layout.setVerticalSpacing(6)
            layout.setHorizontalSpacing(10)
            layout.setContentsMargins(8, 8, 8, 8)
            content.setVisible(False)

            def sync_collapsed_state(checked: bool) -> None:
                toggle.setArrowType(
                    QtCore.Qt.ArrowType.DownArrow
                    if checked
                    else QtCore.Qt.ArrowType.RightArrow
                )
                content.setVisible(checked)

            toggle.toggled.connect(sync_collapsed_state)
            parent_layout.addWidget(toggle)
            parent_layout.addWidget(content)
            return layout

        def _add_advanced_heading(self, layout: QtWidgets.QFormLayout, text: str) -> None:
            label = QtWidgets.QLabel(text)
            label.setStyleSheet("color: #5f6872; font-weight: 600; padding-top: 4px;")
            layout.addRow(label)

        def _make_sweep_grid(
            self,
            first_label: str,
            second_label: str,
        ) -> tuple[
            QtWidgets.QWidget,
            tuple[QtWidgets.QDoubleSpinBox, QtWidgets.QDoubleSpinBox, QtWidgets.QDoubleSpinBox],
            tuple[QtWidgets.QDoubleSpinBox, QtWidgets.QDoubleSpinBox, QtWidgets.QDoubleSpinBox],
        ]:
            group = QtWidgets.QWidget()
            layout = QtWidgets.QGridLayout(group)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setHorizontalSpacing(6)
            layout.setVerticalSpacing(3)

            for column, text in enumerate(("Start", "End", "Step"), start=1):
                header = QtWidgets.QLabel(text)
                header.setStyleSheet("color: #5f6872;")
                header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(header, 0, column)

            first = self._make_sweep_row(layout, 1, first_label)
            second = self._make_sweep_row(layout, 2, second_label)
            layout.setColumnStretch(0, 0)
            for column in (1, 2, 3):
                layout.setColumnStretch(column, 1)
            return group, first, second

        def _make_sweep_row(
            self,
            layout: QtWidgets.QGridLayout,
            row: int,
            label_text: str,
        ) -> tuple[QtWidgets.QDoubleSpinBox, QtWidgets.QDoubleSpinBox, QtWidgets.QDoubleSpinBox]:
            label = QtWidgets.QLabel(label_text)
            label.setStyleSheet("color: #374151;")
            label.setMinimumWidth(46)
            layout.addWidget(label, row, 0)
            start = self._make_number_input(0.0)
            end = self._make_number_input(0.0)
            step = self._make_number_input(1.0)
            layout.addWidget(start, row, 1)
            layout.addWidget(end, row, 2)
            layout.addWidget(step, row, 3)
            return start, end, step

        def _make_vector_inputs(
            self,
        ) -> tuple[
            QtWidgets.QWidget,
            QtWidgets.QDoubleSpinBox,
            QtWidgets.QDoubleSpinBox,
            QtWidgets.QDoubleSpinBox,
        ]:
            group = QtWidgets.QWidget()
            layout = QtWidgets.QGridLayout(group)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setHorizontalSpacing(6)
            labels = ("X", "Y", "Z")
            fields = (
                self._make_number_input(1.0),
                self._make_number_input(0.0),
                self._make_number_input(0.0),
            )
            for column, (label, field) in enumerate(zip(labels, fields, strict=True)):
                header = QtWidgets.QLabel(label)
                header.setStyleSheet("color: #5f6872;")
                header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(header, 0, column)
                layout.addWidget(field, 1, column)
                layout.setColumnStretch(column, 1)
            return group, fields[0], fields[1], fields[2]

        def _make_number_input(self, value: float) -> QtWidgets.QDoubleSpinBox:
            field = FlexibleDoubleSpinBox()
            field.setRange(-1.0e6, 1.0e6)
            field.setDecimals(6)
            field.setSingleStep(1.0)
            field.setValue(value)
            field.setMinimumWidth(70)
            return field

        def _axis_combo(self, default: str):
            combo = QtWidgets.QComboBox()
            combo.setMinimumWidth(62)
            for axis in AXIS_CHOICES:
                combo.addItem(axis.upper(), axis)
            index = combo.findData(default)
            if index >= 0:
                combo.setCurrentIndex(index)
            return combo

        def _create_viewer(self) -> QtWidgets.QWidget:
            try:
                from pyvistaqt import QtInteractor
            except ImportError:
                placeholder = QtWidgets.QTextEdit()
                placeholder.setReadOnly(True)
                placeholder.setText(
                    "3D viewer dependencies are not installed.\n"
                    "Run: uv sync --extra gui"
                )
                return placeholder

            self._plotter = QtInteractor(self)
            self._plotter.set_background("white")
            self._configure_scene_lighting()
            self._plotter.add_axes()
            self._plotter.show_grid()
            self._plotter.enable_parallel_projection()
            return self._plotter

        def _browse_file(self) -> None:
            file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Open CAD file",
                "",
                "CAD Files (*.stl *.step *.stp);;All Files (*)",
            )
            if file_name:
                self.file_edit.setText(file_name)
                self._clear_component_filters()
                self._load_model()

        def _request(self) -> CalculationRequest:
            path = Path(self.file_edit.text()).expanduser()
            if not path.exists():
                raise ValueError(f"File does not exist: {path}")
            mesh_deflection: float | str = (
                "auto" if self.mesh_deflection_auto.isChecked() else self.mesh_deflection.value()
            )
            return CalculationRequest(
                file=path,
                attitude_mode=self.attitude_mode.currentData(),
                input_unit=self.input_unit.currentText(),
                output_unit=self.output_unit.currentText(),
                mesh_deflection=mesh_deflection,
                angular_deflection=self.angular_deflection.value(),
                step_metric_source=self.step_metrics.currentData(),
                roll_start=self.roll_start.value(),
                roll_end=self.roll_end.value(),
                roll_step=self.roll_step.value(),
                alpha_start=self.alpha_start.value(),
                alpha_end=self.alpha_end.value(),
                alpha_step=self.alpha_step.value(),
                beta_start=self.beta_start.value(),
                beta_end=self.beta_end.value(),
                beta_step=self.beta_step.value(),
                pitch_start=self.pitch_start.value(),
                pitch_end=self.pitch_end.value(),
                pitch_step=self.pitch_step.value(),
                vector_x=self.vector_x.value(),
                vector_y=self.vector_y.value(),
                vector_z=self.vector_z.value(),
                axis_map=self._axis_map(),
                step_components=self._selected_step_components(path),
            )

        def _axis_map(self) -> str:
            return ",".join(
                [
                    self.axis_x.currentData(),
                    self.axis_y.currentData(),
                    self.axis_z.currentData(),
                ]
            )

        def _apply_advanced_settings(self) -> None:
            if not self.file_edit.text().strip():
                self._show_error("Select a model file before applying advanced settings.")
                return
            self._load_model()

        def _load_model(self) -> bool:
            try:
                request = self._request()
                self._model = inspect_model(
                    request.file,
                    input_unit=request.input_unit,
                    output_unit=request.output_unit,
                    mesh_deflection=request.mesh_deflection,
                    angular_deflection=request.angular_deflection,
                    step_metric_source=request.step_metric_source,
                    axis_map=request.axis_map,
                    step_components=request.step_components,
                )
            except Exception as exc:
                self._show_error(str(exc))
                return False
            self._populate_component_filters(self._model)
            self._show_model_info(self._model)
            self._plot_model(self._model)
            self._update_projection_vector()
            self.status.setText("Model loaded")
            return True

        def _start_calculation(self) -> None:
            try:
                request = self._request()
            except Exception as exc:
                self._show_error(str(exc))
                return

            if not self._load_model():
                return

            self._set_running(True)
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self.status.setText("Running")
            self._thread = QtCore.QThread(self)
            self._worker = CalculationWorker(request)
            self._worker.moveToThread(self._thread)
            self._thread.started.connect(self._worker.run)
            self._worker.finished.connect(self._on_finished)
            self._worker.failed.connect(self._on_failed)
            self._worker.cancelled.connect(self._on_cancelled)
            self._worker.progress.connect(self._on_progress)
            self._worker.finished.connect(self._thread.quit)
            self._worker.failed.connect(self._thread.quit)
            self._worker.cancelled.connect(self._thread.quit)
            self._thread.finished.connect(self._worker.deleteLater)
            self._thread.finished.connect(self._thread.deleteLater)
            self._thread.finished.connect(self._clear_thread)
            self._thread.start()

        def _cancel_calculation(self) -> None:
            if self._worker is not None:
                self._worker.cancel()
                self.status.setText("Cancelling")

        def _on_progress(
            self,
            index: int,
            total: int,
            description: str,
        ) -> None:
            self.progress.setRange(0, total)
            self.progress.setValue(index)
            self.status.setText(f"Sweep {index}/{total}: {description}")

        def _on_finished(self, rows: list[MeasurementRow]) -> None:
            self._rows = rows
            self._fill_table(rows)
            self._set_running(False)
            self.progress.setRange(0, max(len(rows), 1))
            self.progress.setValue(len(rows))
            self.status.setText(f"Done: {len(rows)} row(s)")
            if rows:
                self.table.selectRow(len(rows) - 1)
                self._update_projection_vector(rows[-1], align_camera=True)

        def _on_failed(self, message: str) -> None:
            self._set_running(False)
            self._show_error(message)

        def _on_cancelled(self) -> None:
            self._set_running(False)
            self.status.setText("Cancelled")

        def _clear_thread(self) -> None:
            self._thread = None
            self._worker = None

        def _save_csv(self) -> None:
            if not self._rows:
                self._show_error("No calculation results to save.")
                return
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Save CSV",
                "cadmetrics_results.csv",
                "CSV Files (*.csv);;All Files (*)",
            )
            if not path:
                return
            try:
                write_rows_csv(path, self._rows)
            except Exception as exc:
                self._show_error(str(exc))
                return
            self.status.setText(f"Saved CSV: {path}")

        def _clear_component_filters(self) -> None:
            self._component_filter_path = None
            self._component_checkboxes = []
            while self.component_list_layout.count():
                item = self.component_list_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            self.component_summary.setText("Load a multi-solid STEP file.")
            self._sync_component_controls(False)

        def _populate_component_filters(self, model: ModelData) -> None:
            current_selected = set(self._selected_step_components(model.path) or ())
            if not current_selected:
                current_selected = set(model.selected_components)
            while self.component_list_layout.count():
                item = self.component_list_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            self._component_checkboxes = []
            self._component_filter_path = model.path
            component_count = len(model.component_names)
            if component_count <= 1:
                message = (
                    "Single STEP component."
                    if model.source_format == "step"
                    else "Component filters are available for STEP files."
                )
                self.component_summary.setText(message)
                self._sync_component_controls(False)
                return

            selected = set(model.selected_components) if model.selected_components else current_selected
            self.component_summary.setText(
                f"{len(selected)} of {component_count} components enabled."
            )
            for index, name in enumerate(model.component_names, start=1):
                checkbox = QtWidgets.QCheckBox(f"{index}: {name}")
                checkbox.setProperty("component_index", index)
                checkbox.setChecked(index in selected)
                checkbox.toggled.connect(self._sync_component_summary)
                self.component_list_layout.addWidget(checkbox)
                self._component_checkboxes.append(checkbox)
            self.component_list_layout.addStretch(1)
            self._sync_component_controls(True)

        def _selected_step_components(self, path: Path) -> tuple[int, ...] | None:
            if not self._component_checkboxes:
                return None
            if self._component_filter_path is None or path != self._component_filter_path:
                return None
            selected = tuple(
                int(checkbox.property("component_index"))
                for checkbox in self._component_checkboxes
                if checkbox.isChecked()
            )
            if not selected:
                raise ValueError("Select at least one STEP component.")
            return selected

        def _set_all_components(self, checked: bool) -> None:
            for checkbox in self._component_checkboxes:
                checkbox.setChecked(checked)
            self._sync_component_summary()

        def _sync_component_summary(self) -> None:
            total = len(self._component_checkboxes)
            if total == 0:
                return
            selected = sum(1 for checkbox in self._component_checkboxes if checkbox.isChecked())
            self.component_summary.setText(f"{selected} of {total} components enabled.")

        def _sync_component_controls(self, enabled: bool) -> None:
            self.component_all_button.setEnabled(enabled)
            self.component_none_button.setEnabled(enabled)

        def _plot_model(self, model: ModelData) -> None:
            if self._plotter is None:
                return
            import pyvista as pv

            faces = np.column_stack(
                [
                    np.full(model.faces.shape[0], 3, dtype=np.int64),
                    model.faces,
                ]
            ).ravel()
            mesh = pv.PolyData(model.vertices, faces)
            self._mesh_polydata = mesh
            self._plotter.clear()
            self._vector_actor = None
            self._centroid_actor = None
            self._overlay_actor = None
            self._feature_edges_actor = None
            self._configure_scene_lighting()
            self._plotter.add_axes()
            self._plotter.show_grid()
            self._mesh_actor = self._plotter.add_mesh(
                mesh,
                color="#9fc8ef",
                show_edges=self.mesh_edges.isChecked(),
                edge_color="#111111",
                opacity=self._shape_opacity(),
                smooth_shading=True,
                split_sharp_edges=True,
                ambient=0.35,
                diffuse=0.72,
                specular=0.18,
                specular_power=24,
            )
            self._apply_mesh_shading()
            self._update_feature_edges()
            self._set_default_model_camera(model)
            self._update_overlay()

        def _set_default_model_camera(self, model: ModelData) -> None:
            if self._plotter is None:
                return
            position, focal_point, view_up = _default_camera_geometry(model.vertices)
            self._plotter.reset_camera()
            self._plotter.camera_position = (
                tuple(position),
                tuple(focal_point),
                tuple(view_up),
            )
            self._plotter.enable_parallel_projection()
            try:
                self._plotter.reset_camera_clipping_range()
            except AttributeError:
                pass

        def _configure_scene_lighting(self) -> None:
            if self._plotter is None:
                return
            try:
                self._plotter.remove_all_lights()
            except Exception:
                pass

            try:
                import pyvista as pv

                key_light = pv.Light(
                    position=(2.5, -3.0, 4.0),
                    focal_point=(0.0, 0.0, 0.0),
                    color="white",
                    intensity=1.1,
                    positional=False,
                )
                fill_light = pv.Light(
                    position=(-3.0, 2.5, 2.0),
                    focal_point=(0.0, 0.0, 0.0),
                    color="white",
                    intensity=0.65,
                    positional=False,
                )
                head_light = pv.Light(light_type="headlight", intensity=0.35)
                self._plotter.add_light(key_light)
                self._plotter.add_light(fill_light)
                self._plotter.add_light(head_light)
            except Exception:
                try:
                    self._plotter.enable_lightkit()
                except Exception:
                    pass

        def _shape_opacity(self) -> float:
            return 0.45 if self.transparent_shape.isChecked() else 1.0

        def _apply_display_options(self, _checked: bool | None = None) -> None:
            if self._plotter is None or self._mesh_actor is None:
                return

            try:
                prop = self._mesh_actor.GetProperty()
            except AttributeError:
                prop = self._mesh_actor.prop
            prop.SetOpacity(self._shape_opacity())
            prop.SetEdgeVisibility(1 if self.mesh_edges.isChecked() else 0)
            prop.SetEdgeColor(0.07, 0.07, 0.07)
            self._apply_mesh_shading(prop)
            self._update_feature_edges(render=False)
            self._plotter.render()

        def _update_feature_edges(self, *, render: bool = True) -> None:
            if self._plotter is None:
                return
            if self._feature_edges_actor is not None:
                try:
                    self._plotter.remove_actor(self._feature_edges_actor)
                except Exception:
                    pass
                self._feature_edges_actor = None

            if self._mesh_polydata is None or not self.feature_edges.isChecked():
                if render:
                    self._plotter.render()
                return

            try:
                edges = self._mesh_polydata.extract_feature_edges(
                    feature_angle=35.0,
                    boundary_edges=True,
                    feature_edges=True,
                    manifold_edges=False,
                    non_manifold_edges=True,
                )
            except Exception:
                if render:
                    self._plotter.render()
                return

            if edges.n_cells <= 0:
                if render:
                    self._plotter.render()
                return

            self._feature_edges_actor = self._plotter.add_mesh(
                edges,
                color="#1d2730",
                line_width=2.5,
                render_lines_as_tubes=True,
                opacity=0.9,
                pickable=False,
            )
            if render:
                self._plotter.render()

        def _apply_mesh_shading(self, prop: Any | None = None) -> None:
            if self._mesh_actor is None:
                return
            if prop is None:
                try:
                    prop = self._mesh_actor.GetProperty()
                except AttributeError:
                    prop = self._mesh_actor.prop
            try:
                prop.SetInterpolationToPhong()
                prop.SetAmbient(0.35)
                prop.SetDiffuse(0.72)
                prop.SetSpecular(0.18)
                prop.SetSpecularPower(24)
            except AttributeError:
                return

        def _save_view_image(self) -> None:
            if self._plotter is None:
                self._show_error("3D viewer is not available.")
                return
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Save View Image",
                "cadmetrics_view.png",
                "PNG Images (*.png);;All Files (*)",
            )
            if not path:
                return
            output_path = Path(path)
            if output_path.suffix == "":
                output_path = output_path.with_suffix(".png")
            try:
                self._plotter.screenshot(str(output_path))
            except Exception as exc:
                self._show_error(str(exc))
                return
            self.status.setText(f"Saved image: {output_path}")

        def _update_overlay(self, _checked: bool | None = None) -> None:
            if self._plotter is None:
                return
            if self._overlay_actor is not None:
                try:
                    self._plotter.remove_actor(self._overlay_actor)
                except Exception:
                    pass
                self._overlay_actor = None
            if not self.show_overlay.isChecked():
                self._plotter.render()
                return
            text = _overlay_text(
                self._overlay_row,
                model=self._model,
                request=self._request_or_none(),
            )
            if not text:
                self._plotter.render()
                return
            self._overlay_actor = self._plotter.add_text(
                text,
                position="upper_left",
                font_size=10,
                color="#111111",
                shadow=True,
            )
            self._plotter.render()

        def _request_or_none(self) -> CalculationRequest | None:
            try:
                return self._request()
            except Exception:
                return None

        def _update_projection_vector(
            self,
            row: MeasurementRow | None = None,
            *,
            align_camera: bool = False,
        ) -> None:
            if self._plotter is None or self._model is None:
                return
            if not isinstance(row, MeasurementRow):
                row = None
            self._overlay_row = row
            if row is not None and row.direction_x is not None:
                direction = np.array([row.direction_x, row.direction_y, row.direction_z], dtype=float)
            else:
                try:
                    request = self._request()
                    if request.attitude_mode == "vector":
                        direction = parse_vector(
                            f"{request.vector_x},{request.vector_y},{request.vector_z}"
                        )
                    elif request.attitude_mode == "roll_pitch":
                        direction = projection_direction_for_orientation(
                            Orientation(
                                roll_deg=request.roll_start,
                                alpha_deg=request.pitch_start,
                                beta_deg=0.0,
                            )
                        )
                    else:
                        direction = projection_direction_for_orientation(
                            Orientation(
                                roll_deg=0.0,
                                alpha_deg=request.alpha_start,
                                beta_deg=request.beta_start,
                            )
                        )
                except Exception:
                    direction = np.array([1.0, 0.0, 0.0], dtype=float)

            through_point = _row_centroid_point(row)
            start, vector = _projection_arrow_geometry(
                self._model.vertices,
                direction,
                through_point=through_point,
            )
            if self._vector_actor is not None:
                try:
                    self._plotter.remove_actor(self._vector_actor)
                except Exception:
                    pass
            self._vector_actor = self._plotter.add_arrows(
                start.reshape(1, 3),
                vector.reshape(1, 3),
                color="#d04a02",
            )
            self._update_centroid_marker(row)
            if align_camera:
                self._look_from_projection_direction(direction)
            self._update_overlay()
            self._plotter.render()

        def _update_centroid_marker(self, row: MeasurementRow | None) -> None:
            if self._plotter is None:
                return
            if self._centroid_actor is not None:
                try:
                    self._plotter.remove_actor(self._centroid_actor)
                except Exception:
                    pass
                self._centroid_actor = None
            if (
                row is None
                or row.centroid_x is None
                or row.centroid_y is None
                or row.centroid_z is None
            ):
                return

            import pyvista as pv

            spans = np.ptp(self._model.vertices, axis=0) if self._model is not None else np.array([1.0])
            radius = max(float(spans.max()) * 0.025, 1.0e-6)
            marker = pv.Sphere(
                radius=radius,
                center=(row.centroid_x, row.centroid_y, row.centroid_z),
                theta_resolution=24,
                phi_resolution=12,
            )
            self._centroid_actor = self._plotter.add_mesh(
                marker,
                color="#ffd400",
                edge_color="#111111",
                show_edges=True,
            )

        def _look_from_projection_direction(self, direction: np.ndarray) -> None:
            if self._plotter is None or self._model is None:
                return
            position, focal_point, view_up = _projection_camera_geometry(
                self._model.vertices,
                direction,
            )
            self._plotter.camera_position = (
                tuple(position),
                tuple(focal_point),
                tuple(view_up),
            )
            self._plotter.enable_parallel_projection()

        def _on_table_selection_changed(self) -> None:
            row_index = self.table.currentRow()
            if row_index < 0 or row_index >= len(self._rows):
                return
            self._update_projection_vector(self._rows[row_index], align_camera=True)

        def _fill_table(self, rows: list[MeasurementRow]) -> None:
            self.table.setRowCount(len(rows))
            self.result_count.setText(f"Rows: {len(rows)}")
            for row_index, row in enumerate(rows):
                data = row.to_csv_row()
                for column_index, key in enumerate(TABLE_COLUMNS):
                    value = data.get(key)
                    item = QtWidgets.QTableWidgetItem(_format_cell(value))
                    self.table.setItem(row_index, column_index, item)
            self.table.resizeColumnsToContents()

        def _show_model_info(self, model: ModelData) -> None:
            lines = [
                f"file: {model.path.name}",
                f"format/unit: {model.source_format}, {model.output_unit}",
                f"metrics: {model.step_metric_source or 'mesh'}",
                f"mesh: {model.vertex_count} vertices, {model.face_count} faces",
                "bounds: "
                f"X[{_format_cell(model.x_min)}, {_format_cell(model.x_max)}], "
                f"Y[{_format_cell(model.y_min)}, {_format_cell(model.y_max)}], "
                f"Z[{_format_cell(model.z_min)}, {_format_cell(model.z_max)}]",
                f"surface_area: {_format_cell(model.surface_area)}",
                f"volume: {_format_cell(model.volume)}",
                f"cadmetrics_version: {model.cadmetrics_version}",
                f"cadmetrics_hash: {model.cadmetrics_hash}",
                f"watertight: {_format_cell(model.is_watertight)}",
            ]
            if model.component_names:
                lines.insert(
                    3,
                    "components: "
                    f"{len(model.selected_components)} of {len(model.component_names)} selected",
                )
            if model.warnings:
                lines.append(f"warnings: {'; '.join(model.warnings)}")
            self.model_info.setText("\n".join(lines))

        def _sync_attitude_controls(self) -> None:
            mode = self.attitude_mode.currentData()
            self.alpha_beta_group.setVisible(mode == "alpha_beta")
            self.roll_pitch_group.setVisible(mode == "roll_pitch")
            self.vector_group.setVisible(mode == "vector")

        def _sync_mesh_deflection_controls(self) -> None:
            self.mesh_deflection.setEnabled(not self.mesh_deflection_auto.isChecked())

        def _set_running(self, running: bool) -> None:
            self.run_button.setEnabled(not running)
            self.save_button.setEnabled(not running and bool(self._rows))
            self.cancel_button.setEnabled(running)
            self.cancel_button.setVisible(running)

        def _show_error(self, message: str) -> None:
            self.status.setText(f"Error: {message}")
            QtWidgets.QMessageBox.critical(self, "cadmetrics error", message)

else:
    MainWindow = object  # type: ignore[misc,assignment]


def _format_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)


def _overlay_text(
    row: MeasurementRow | None,
    *,
    model: ModelData | None,
    request: CalculationRequest | None,
) -> str:
    if row is not None:
        lines = [
            "cadmetrics result",
            f"file: {Path(row.file).name}",
            f"unit: {row.output_unit}",
            f"roll/pitch: {_format_angle(row.roll_deg)}, {_format_angle(row.pitch_deg)} deg",
            f"alpha/beta: {_format_angle(row.alpha_deg)}, {_format_angle(row.beta_deg)} deg",
        ]
        if row.direction_x is not None:
            lines.append(
                "direction: "
                f"({_format_vector_value(row.direction_x)}, "
                f"{_format_vector_value(row.direction_y)}, "
                f"{_format_vector_value(row.direction_z)})"
            )
        lines.extend(
            [
                "bounds: "
                f"X[{_format_metric(row.x_min)}, {_format_metric(row.x_max)}], "
                f"Y[{_format_metric(row.y_min)}, {_format_metric(row.y_max)}], "
                f"Z[{_format_metric(row.z_min)}, {_format_metric(row.z_max)}]",
                f"surface_area: {_format_metric(row.surface_area)}",
                f"volume: {_format_metric(row.volume)}",
                f"projected_area: {_format_metric(row.projected_area)}",
                "centroid: "
                f"({_format_vector_value(row.centroid_x)}, "
                f"{_format_vector_value(row.centroid_y)}, "
                f"{_format_vector_value(row.centroid_z)})",
            ]
        )
        if row.method:
            lines.append(f"method: {row.method}")
        lines.append(f"cadmetrics_version: {row.cadmetrics_version}")
        lines.append(f"cadmetrics_hash: {row.cadmetrics_hash}")
        if row.warnings:
            lines.append(f"warnings: {'; '.join(row.warnings)}")
        return "\n".join(lines)

    if model is None and request is None:
        return ""

    lines = ["cadmetrics view"]
    if model is not None:
        lines.extend(
            [
                f"file: {model.path.name}",
                f"format: {model.source_format}",
                f"unit: {model.output_unit}",
                "bounds: "
                f"X[{_format_metric(model.x_min)}, {_format_metric(model.x_max)}], "
                f"Y[{_format_metric(model.y_min)}, {_format_metric(model.y_max)}], "
                f"Z[{_format_metric(model.z_min)}, {_format_metric(model.z_max)}]",
                f"surface_area: {_format_metric(model.surface_area)}",
                f"volume: {_format_metric(model.volume)}",
                f"cadmetrics_version: {model.cadmetrics_version}",
                f"cadmetrics_hash: {model.cadmetrics_hash}",
            ]
        )
    if request is not None:
        lines.append(f"input: {request.attitude_mode}")
        if request.attitude_mode == "roll_pitch":
            lines.extend(
                [
                    f"roll: {_format_sweep(request.roll_start, request.roll_end, request.roll_step)} deg",
                    f"pitch: {_format_sweep(request.pitch_start, request.pitch_end, request.pitch_step)} deg",
                ]
            )
        elif request.attitude_mode == "vector":
            lines.append(
                "direction: "
                f"({_format_vector_value(request.vector_x)}, "
                f"{_format_vector_value(request.vector_y)}, "
                f"{_format_vector_value(request.vector_z)})"
            )
        else:
            lines.extend(
                [
                    f"alpha: {_format_sweep(request.alpha_start, request.alpha_end, request.alpha_step)} deg",
                    f"beta: {_format_sweep(request.beta_start, request.beta_end, request.beta_step)} deg",
                ]
            )
    return "\n".join(lines)


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6g}"


def _format_angle(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3g}"


def _format_vector_value(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4g}"


def _format_sweep(start: float, end: float, step: float) -> str:
    if start == end:
        return f"{start:.3g}"
    return f"{start:.3g}:{end:.3g}:{step:.3g}"


def _row_centroid_point(row: MeasurementRow | None) -> np.ndarray | None:
    if row is None or row.centroid_x is None or row.centroid_y is None or row.centroid_z is None:
        return None
    return np.array([row.centroid_x, row.centroid_y, row.centroid_z], dtype=float)


def _projection_arrow_geometry(
    vertices: np.ndarray,
    direction: np.ndarray,
    *,
    through_point: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    anchor = vertices.mean(axis=0) if through_point is None else through_point
    unit_direction = direction / np.linalg.norm(direction)
    spans = np.ptp(vertices, axis=0)
    scale = max(float(spans.max()), 1.0)
    clearance = scale * 0.15
    projections = (vertices - anchor) @ unit_direction
    upstream_edge = float(projections.min())
    arrow_length = scale * 0.35
    start = anchor + unit_direction * (upstream_edge - clearance - arrow_length)
    vector = unit_direction * arrow_length
    return start, vector


def _projection_camera_geometry(
    vertices: np.ndarray,
    direction: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = vertices.mean(axis=0)
    unit_direction = direction / np.linalg.norm(direction)
    spans = np.ptp(vertices, axis=0)
    scale = max(float(spans.max()), 1.0)
    distance = scale * 3.0
    _, view_up = projection_basis(unit_direction)
    position = center - unit_direction * distance
    return position, center, view_up


def _default_camera_geometry(vertices: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = vertices.mean(axis=0)
    from_direction = np.array([-1.0, -1.0, 1.0], dtype=float)
    from_direction = from_direction / np.linalg.norm(from_direction)
    spans = np.ptp(vertices, axis=0)
    scale = max(float(spans.max()), 1.0)
    distance = scale * 3.0
    position = center + from_direction * distance
    view_direction = (center - position) / np.linalg.norm(center - position)
    up_hint = np.array([0.0, 0.0, 1.0], dtype=float)
    view_up = up_hint - view_direction * float(np.dot(up_hint, view_direction))
    view_up = view_up / np.linalg.norm(view_up)
    return position, center, view_up
