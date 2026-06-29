from __future__ import annotations

import sys
from pathlib import Path
from threading import Event
from typing import Any

import numpy as np

from cadmetrics.api import inspect_model
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
    "alpha_deg",
    "beta_deg",
    "direction_x",
    "direction_y",
    "direction_z",
    "volume",
    "surface_area",
    "projected_area",
    "is_watertight",
    "method",
    "elapsed_sec",
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
            text = f"{value:.6f}".rstrip("0").rstrip(".")
            if "." not in text:
                text = f"{text}.0"
            return text

else:
    CalculationWorker = object  # type: ignore[misc,assignment]
    FlexibleDoubleSpinBox = object  # type: ignore[misc,assignment]


class _CancelledCalculation(Exception):
    pass


def main() -> None:
    if QtWidgets is None:
        raise MissingGuiDependency(
            "PySide6 GUI dependencies are not installed. Run: uv sync --extra gui-pyside"
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

            self._build_ui()
            self._set_running(False)

        def _build_ui(self) -> None:
            root = QtWidgets.QSplitter()
            root.setOrientation(QtCore.Qt.Orientation.Horizontal)
            self.setCentralWidget(root)

            controls = QtWidgets.QWidget()
            controls.setMinimumWidth(390)
            controls.setMaximumWidth(500)
            form = QtWidgets.QFormLayout(controls)
            form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            form.setVerticalSpacing(8)

            self.file_edit = QtWidgets.QLineEdit()
            self.file_edit.setPlaceholderText("STL or STEP file")
            browse = QtWidgets.QPushButton("Browse")
            browse.clicked.connect(self._browse_file)
            file_row = QtWidgets.QHBoxLayout()
            file_row.addWidget(self.file_edit)
            file_row.addWidget(browse)
            form.addRow("File", file_row)

            self.input_unit = QtWidgets.QComboBox()
            self.input_unit.addItems(UNIT_OPTIONS)
            form.addRow("Input unit", self.input_unit)

            self.output_unit = QtWidgets.QComboBox()
            self.output_unit.addItems(OUTPUT_UNIT_OPTIONS)
            form.addRow("Output unit", self.output_unit)

            self.mesh_deflection = QtWidgets.QDoubleSpinBox()
            self.mesh_deflection.setRange(1.0e-8, 1.0)
            self.mesh_deflection.setDecimals(4)
            self.mesh_deflection.setValue(1.0e-3)
            form.addRow("Mesh deflection", self.mesh_deflection)

            self.angular_deflection = QtWidgets.QDoubleSpinBox()
            self.angular_deflection.setRange(1.0e-6, 1.0)
            self.angular_deflection.setDecimals(2)
            self.angular_deflection.setValue(0.1)
            form.addRow("Angular deflection", self.angular_deflection)

            self.attitude_box = QtWidgets.QGroupBox("Attitude")
            attitude_form = QtWidgets.QFormLayout(self.attitude_box)
            attitude_form.setFieldGrowthPolicy(
                QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )
            attitude_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            attitude_form.setVerticalSpacing(6)
            form.addRow(self.attitude_box)

            self.attitude_mode = QtWidgets.QComboBox()
            self.attitude_mode.addItem("Alpha / Beta", "alpha_beta")
            self.attitude_mode.addItem("Roll / Pitch", "roll_pitch")
            self.attitude_mode.addItem("Unit vector", "vector")
            self.attitude_mode.currentIndexChanged.connect(self._sync_attitude_controls)
            self.attitude_mode.currentIndexChanged.connect(self._update_projection_vector)
            attitude_form.addRow("Input", self.attitude_mode)

            self.roll_group, self.roll_start, self.roll_end, self.roll_step = (
                self._make_sweep_angle_inputs()
            )
            self.alpha_group, self.alpha_start, self.alpha_end, self.alpha_step = (
                self._make_sweep_angle_inputs()
            )
            self.beta_group, self.beta_start, self.beta_end, self.beta_step = (
                self._make_sweep_angle_inputs()
            )
            self.pitch_group, self.pitch_start, self.pitch_end, self.pitch_step = (
                self._make_sweep_angle_inputs()
            )
            self.vector_x = self._make_number_input(1.0)
            self.vector_y = self._make_number_input(0.0)
            self.vector_z = self._make_number_input(0.0)

            self.roll_label = QtWidgets.QLabel("Roll")
            self.alpha_label = QtWidgets.QLabel("Alpha")
            self.beta_label = QtWidgets.QLabel("Beta")
            self.pitch_label = QtWidgets.QLabel("Pitch")
            self.vector_x_label = QtWidgets.QLabel("Vector X")
            self.vector_y_label = QtWidgets.QLabel("Vector Y")
            self.vector_z_label = QtWidgets.QLabel("Vector Z")
            attitude_form.addRow(self.roll_label, self.roll_group)
            attitude_form.addRow(self.alpha_label, self.alpha_group)
            attitude_form.addRow(self.beta_label, self.beta_group)
            attitude_form.addRow(self.pitch_label, self.pitch_group)
            attitude_form.addRow(self.vector_x_label, self.vector_x)
            attitude_form.addRow(self.vector_y_label, self.vector_y)
            attitude_form.addRow(self.vector_z_label, self.vector_z)

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

            button_row = QtWidgets.QHBoxLayout()
            self.run_button = QtWidgets.QPushButton("Run Sweep")
            self.run_button.clicked.connect(self._start_calculation)
            self.cancel_button = QtWidgets.QPushButton("Cancel")
            self.cancel_button.clicked.connect(self._cancel_calculation)
            button_row.addWidget(self.run_button)
            button_row.addWidget(self.cancel_button)
            form.addRow("", button_row)

            self.save_button = QtWidgets.QPushButton("Save CSV")
            self.save_button.clicked.connect(self._save_csv)
            form.addRow("", self.save_button)

            self.progress = QtWidgets.QProgressBar()
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            form.addRow("Progress", self.progress)

            self.status = QtWidgets.QLabel("Ready")
            self.status.setWordWrap(True)
            form.addRow("Status", self.status)

            self.model_info = QtWidgets.QTextEdit()
            self.model_info.setReadOnly(True)
            self.model_info.setMinimumHeight(130)
            form.addRow("Model", self.model_info)

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
            self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
            right.addWidget(self.table)
            right.setSizes([560, 260])

            root.addWidget(controls)
            root.addWidget(right)
            root.setSizes([400, 920])
            self._sync_attitude_controls()

        def _make_sweep_angle_inputs(
            self,
        ) -> tuple[
            QtWidgets.QWidget,
            QtWidgets.QDoubleSpinBox,
            QtWidgets.QDoubleSpinBox,
            QtWidgets.QDoubleSpinBox,
        ]:
            group = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(group)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            start = self._make_number_input(0.0)
            end = self._make_number_input(0.0)
            step = self._make_number_input(1.0)
            layout.addWidget(QtWidgets.QLabel("Start"))
            layout.addWidget(start)
            layout.addWidget(QtWidgets.QLabel("End"))
            layout.addWidget(end)
            layout.addWidget(QtWidgets.QLabel("Step"))
            layout.addWidget(step)
            return group, start, end, step

        def _make_number_input(self, value: float) -> QtWidgets.QDoubleSpinBox:
            field = FlexibleDoubleSpinBox()
            field.setRange(-1.0e6, 1.0e6)
            field.setDecimals(6)
            field.setSingleStep(1.0)
            field.setValue(value)
            field.setMinimumWidth(72)
            return field

        def _create_viewer(self) -> QtWidgets.QWidget:
            try:
                from pyvistaqt import QtInteractor
            except ImportError:
                placeholder = QtWidgets.QTextEdit()
                placeholder.setReadOnly(True)
                placeholder.setText(
                    "3D viewer dependencies are not installed.\n"
                    "Run: uv sync --extra gui-pyside"
                )
                return placeholder

            self._plotter = QtInteractor(self)
            self._plotter.set_background("white")
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
                self._load_model()

        def _request(self) -> CalculationRequest:
            path = Path(self.file_edit.text()).expanduser()
            if not path.exists():
                raise ValueError(f"File does not exist: {path}")
            return CalculationRequest(
                file=path,
                attitude_mode=self.attitude_mode.currentData(),
                input_unit=self.input_unit.currentText(),
                output_unit=self.output_unit.currentText(),
                mesh_deflection=self.mesh_deflection.value(),
                angular_deflection=self.angular_deflection.value(),
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
            )

        def _load_model(self) -> bool:
            try:
                request = self._request()
                self._model = inspect_model(
                    request.file,
                    input_unit=request.input_unit,
                    output_unit=request.output_unit,
                    mesh_deflection=request.mesh_deflection,
                    angular_deflection=request.angular_deflection,
                )
            except Exception as exc:
                self._show_error(str(exc))
                return False
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
            self._plotter.clear()
            self._vector_actor = None
            self._plotter.add_axes()
            self._plotter.show_grid()
            self._mesh_actor = self._plotter.add_mesh(
                mesh,
                color="#8fb4dd",
                show_edges=True,
                edge_color="#3f5870",
                opacity=0.92,
            )
            self._plotter.reset_camera()
            self._plotter.enable_parallel_projection()

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

            start, vector = _projection_arrow_geometry(self._model.vertices, direction)
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
            if align_camera:
                self._look_from_projection_direction(direction)
            self._plotter.render()

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
            for row_index, row in enumerate(rows):
                data = row.to_csv_row()
                for column_index, key in enumerate(TABLE_COLUMNS):
                    value = data.get(key)
                    item = QtWidgets.QTableWidgetItem(_format_cell(value))
                    self.table.setItem(row_index, column_index, item)
            self.table.resizeColumnsToContents()

        def _show_model_info(self, model: ModelData) -> None:
            lines = [
                f"file: {model.path}",
                f"format: {model.source_format}",
                f"input_unit: {model.input_unit}",
                f"output_unit: {model.output_unit}",
                f"vertices: {model.vertex_count}",
                f"faces: {model.face_count}",
                f"volume: {_format_cell(model.volume)}",
                f"surface_area: {_format_cell(model.surface_area)}",
                f"is_watertight: {_format_cell(model.is_watertight)}",
                f"warnings: {'; '.join(model.warnings)}",
            ]
            self.model_info.setText("\n".join(lines))

        def _sync_attitude_controls(self) -> None:
            mode = self.attitude_mode.currentData()
            self._set_row_visible(self.alpha_label, self.alpha_group, mode == "alpha_beta")
            self._set_row_visible(self.beta_label, self.beta_group, mode == "alpha_beta")
            self._set_row_visible(self.roll_label, self.roll_group, mode == "roll_pitch")
            self._set_row_visible(self.pitch_label, self.pitch_group, mode == "roll_pitch")
            self._set_row_visible(self.vector_x_label, self.vector_x, mode == "vector")
            self._set_row_visible(self.vector_y_label, self.vector_y, mode == "vector")
            self._set_row_visible(self.vector_z_label, self.vector_z, mode == "vector")

        def _set_running(self, running: bool) -> None:
            self.run_button.setEnabled(not running)
            self.save_button.setEnabled(not running and bool(self._rows))
            self.cancel_button.setEnabled(running)

        def _set_row_visible(
            self,
            label: QtWidgets.QLabel,
            field: QtWidgets.QWidget,
            visible: bool,
        ) -> None:
            label.setVisible(visible)
            field.setVisible(visible)

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


def _projection_arrow_geometry(vertices: np.ndarray, direction: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    center = vertices.mean(axis=0)
    unit_direction = direction / np.linalg.norm(direction)
    spans = np.ptp(vertices, axis=0)
    scale = max(float(spans.max()), 1.0)
    arrow_length = scale * 0.35
    clearance = scale * 0.15
    projections = (vertices - center) @ unit_direction
    upstream_edge = float(projections.min())
    start = center + unit_direction * (upstream_edge - clearance - arrow_length)
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
