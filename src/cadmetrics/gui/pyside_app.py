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
        progress = QtCore.Signal(int, int, float, float, float)
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

        def _on_progress(self, index: int, total: int, orientation: Orientation) -> None:
            if self._cancel.is_set():
                raise _CancelledCalculation
            self.progress.emit(
                index,
                total,
                orientation.roll_deg,
                orientation.alpha_deg,
                orientation.beta_deg,
            )

else:
    CalculationWorker = object  # type: ignore[misc,assignment]


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
            controls.setMinimumWidth(360)
            controls.setMaximumWidth(460)
            form = QtWidgets.QFormLayout(controls)
            form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

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
            self.mesh_deflection.setDecimals(8)
            self.mesh_deflection.setValue(1.0e-3)
            form.addRow("Mesh deflection", self.mesh_deflection)

            self.angular_deflection = QtWidgets.QDoubleSpinBox()
            self.angular_deflection.setRange(1.0e-6, 1.0)
            self.angular_deflection.setDecimals(6)
            self.angular_deflection.setValue(0.1)
            form.addRow("Angular deflection", self.angular_deflection)

            self.mode = QtWidgets.QComboBox()
            self.mode.addItems(["measure", "project", "sweep"])
            self.mode.currentTextChanged.connect(self._sync_mode_controls)
            form.addRow("Mode", self.mode)

            self.roll = QtWidgets.QLineEdit("0")
            self.alpha = QtWidgets.QLineEdit("0")
            self.beta = QtWidgets.QLineEdit("0")
            form.addRow("Roll", self.roll)
            form.addRow("Alpha", self.alpha)
            form.addRow("Beta", self.beta)

            self.direction = QtWidgets.QLineEdit()
            self.direction.setPlaceholderText("Optional: 1,0,0")
            form.addRow("Direction", self.direction)

            angle_note = QtWidgets.QLabel(
                "Angles describe the projection direction. A Fusion plane angle can be complementary."
            )
            angle_note.setWordWrap(True)
            form.addRow("", angle_note)

            button_row = QtWidgets.QHBoxLayout()
            self.load_button = QtWidgets.QPushButton("Load")
            self.load_button.clicked.connect(self._load_model)
            self.run_button = QtWidgets.QPushButton("Run")
            self.run_button.clicked.connect(self._start_calculation)
            self.cancel_button = QtWidgets.QPushButton("Cancel")
            self.cancel_button.clicked.connect(self._cancel_calculation)
            button_row.addWidget(self.load_button)
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
            right.addWidget(self.table)
            right.setSizes([560, 260])

            root.addWidget(controls)
            root.addWidget(right)
            root.setSizes([400, 920])
            self._sync_mode_controls()

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

        def _request(self) -> CalculationRequest:
            path = Path(self.file_edit.text()).expanduser()
            if not path.exists():
                raise ValueError(f"File does not exist: {path}")
            return CalculationRequest(
                file=path,
                mode=self.mode.currentText(),
                input_unit=self.input_unit.currentText(),
                output_unit=self.output_unit.currentText(),
                mesh_deflection=self.mesh_deflection.value(),
                angular_deflection=self.angular_deflection.value(),
                roll=self.roll.text().strip() or "0",
                alpha=self.alpha.text().strip() or "0",
                beta=self.beta.text().strip() or "0",
                direction=self.direction.text().strip() or None,
            )

        def _load_model(self) -> None:
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
                return
            self._show_model_info(self._model)
            self._plot_model(self._model)
            self._update_projection_vector()
            self.status.setText("Model loaded")

        def _start_calculation(self) -> None:
            try:
                request = self._request()
            except Exception as exc:
                self._show_error(str(exc))
                return

            if self._model is None or self._model.path != request.file:
                self._load_model()

            self._set_running(True)
            self.progress.setRange(0, 0 if request.mode == "measure" else 1)
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
            roll: float,
            alpha: float,
            beta: float,
        ) -> None:
            self.progress.setRange(0, total)
            self.progress.setValue(index)
            self.status.setText(f"Sweep {index}/{total}: roll={roll:g}, alpha={alpha:g}, beta={beta:g}")

        def _on_finished(self, rows: list[MeasurementRow]) -> None:
            self._rows = rows
            self._fill_table(rows)
            self._set_running(False)
            self.progress.setRange(0, max(len(rows), 1))
            self.progress.setValue(len(rows))
            self.status.setText(f"Done: {len(rows)} row(s)")
            self._update_projection_vector(rows[-1] if rows else None)

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

        def _update_projection_vector(self, row: MeasurementRow | None = None) -> None:
            if self._plotter is None or self._model is None:
                return
            if row is not None and row.direction_x is not None:
                direction = np.array([row.direction_x, row.direction_y, row.direction_z], dtype=float)
            else:
                try:
                    request = self._request()
                    if request.direction:
                        direction = parse_vector(request.direction)
                    else:
                        direction = projection_direction_for_orientation(
                            Orientation(
                                roll_deg=float(request.roll),
                                alpha_deg=float(request.alpha),
                                beta_deg=float(request.beta),
                            )
                        )
                except Exception:
                    direction = np.array([1.0, 0.0, 0.0], dtype=float)

            center = self._model.vertices.mean(axis=0)
            spans = np.ptp(self._model.vertices, axis=0)
            scale = max(float(spans.max()), 1.0)
            start = center - direction * scale * 0.6
            vector = direction * scale * 1.2
            self._plotter.add_arrows(start.reshape(1, 3), vector.reshape(1, 3), color="#d04a02")
            self._plotter.render()

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

        def _sync_mode_controls(self) -> None:
            mode = self.mode.currentText()
            sweep_mode = mode == "sweep"
            project_mode = mode == "project"
            self.direction.setEnabled(project_mode)
            self.roll.setPlaceholderText("start:end:step" if sweep_mode else "degrees")
            self.alpha.setPlaceholderText("start:end:step" if sweep_mode else "degrees")
            self.beta.setPlaceholderText("start:end:step" if sweep_mode else "degrees")

        def _set_running(self, running: bool) -> None:
            self.load_button.setEnabled(not running)
            self.run_button.setEnabled(not running)
            self.save_button.setEnabled(not running and bool(self._rows))
            self.cancel_button.setEnabled(running)

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
