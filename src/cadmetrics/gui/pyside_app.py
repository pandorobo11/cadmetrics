from __future__ import annotations

import sys
import tempfile
from contextlib import ExitStack
from importlib import resources
from pathlib import Path
from typing import Any

from cadmetrics.docs_site import build_documentation_site

try:
    from PySide6 import QtCore as _QtCore
    from PySide6 import QtGui as _QtGui
    from PySide6 import QtWidgets as _QtWidgets
except ImportError:  # pragma: no cover - entry point without GUI extra
    _QtCore = None  # type: ignore[assignment]
    _QtGui = None  # type: ignore[assignment]
    _QtWidgets = None  # type: ignore[assignment]

QtCore: Any = _QtCore
QtGui: Any = _QtGui
QtWidgets: Any = _QtWidgets


class MissingGuiDependency(RuntimeError):
    pass


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
    from cadmetrics.gui.calculation_controller import CalculationController
    from cadmetrics.gui.control_panel import ControlPanel
    from cadmetrics.gui.gui_types import OperationState
    from cadmetrics.gui.jobs import CalculationRequest
    from cadmetrics.gui.results_panel import ResultsPanel
    from cadmetrics.gui.styles import application_stylesheet
    from cadmetrics.gui.viewer import ModelViewer
    from cadmetrics.types import MeasurementRow, ModelData

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("cadmetrics")
            self._request: CalculationRequest | None = None
            self._close_when_idle = False
            self._documentation_resources = ExitStack()
            self._documentation_tempdir: tempfile.TemporaryDirectory[str] | None = None
            self._documentation_index: Path | None = None
            self.controller = CalculationController(self)
            self.controls = ControlPanel(self)
            self.viewer = ModelViewer(self)
            self.results = ResultsPanel(self)
            self._build_ui()
            self._build_menu()
            self._connect_components()
            self._on_state_changed(OperationState.IDLE)

        def _build_ui(self) -> None:
            self.setStyleSheet(application_stylesheet())
            root = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
            self.setCentralWidget(root)
            root.addWidget(self.controls)
            right = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
            right.addWidget(self.viewer)
            right.addWidget(self.results)
            right.setSizes([560, 260])
            root.addWidget(right)
            root.setSizes([440, 880])

            self.status = QtWidgets.QLabel("Ready")
            self.progress_bar = QtWidgets.QProgressBar()
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self.progress_bar.setFixedWidth(180)
            self.progress_bar.setTextVisible(False)
            status_bar = QtWidgets.QStatusBar()
            status_bar.addWidget(self.status, 1)
            status_bar.addPermanentWidget(self.progress_bar)
            self.setStatusBar(status_bar)

        def _build_menu(self) -> None:
            help_menu = self.menuBar().addMenu("Help")
            documentation_action = QtGui.QAction("Documentation", self)
            documentation_action.triggered.connect(self._show_documentation)
            help_menu.addAction(documentation_action)

        def _connect_components(self) -> None:
            self.controls.calculation_requested.connect(self._calculate)
            self.controls.model_reload_requested.connect(self._load_model)
            self.controls.cancel_requested.connect(self.controller.cancel)
            self.controls.viewer_options_changed.connect(self.viewer.set_options)
            self.controls.request_changed.connect(self._preview_request)
            self.controls.save_image_button.clicked.connect(self.viewer.choose_and_save_image)
            self.viewer.base_face_available.connect(self._set_base_face_available)
            self.viewer.newly_exposed_surface_available.connect(
                self._set_newly_exposed_surface_available
            )
            self.viewer.error.connect(self._show_error)
            self.viewer.message.connect(self.status.setText)
            self.results.selected_row_changed.connect(self._show_result)
            self.results.error.connect(self._show_error)
            self.controller.model_loaded.connect(self._on_model_loaded)
            self.controller.results_ready.connect(self._on_results_ready)
            self.controller.progress.connect(self._on_progress)
            self.controller.state_changed.connect(self._on_state_changed)
            self.controller.failed.connect(self._show_error)
            self.controller.cancelled.connect(lambda: self.status.setText("Cancelled"))
            self.controller.message.connect(self.status.setText)
            self.controller.shutdown_ready.connect(self._finish_close)

        @QtCore.Slot(object)
        def _calculate(self, request: CalculationRequest) -> None:
            self._request = request
            self.viewer.set_request(request)
            self.controller.calculate(request)

        @QtCore.Slot(object)
        def _load_model(self, request: CalculationRequest) -> None:
            self._request = request
            self.viewer.set_request(request)
            self.controller.load_only(request)

        @QtCore.Slot(object)
        def _preview_request(self, request: CalculationRequest) -> None:
            self._request = request
            self.viewer.set_request(request)

        @QtCore.Slot(object)
        def _on_model_loaded(self, model: ModelData) -> None:
            self.controls.set_model(model)
            self.viewer.set_model(model)
            self.viewer.set_request(self._request)
            self.status.setText("Model loaded")

        @QtCore.Slot(list)
        def _on_results_ready(self, rows: list[MeasurementRow]) -> None:
            self.results.set_rows(rows)
            self.results.select_last_row()
            self.progress_bar.setRange(0, max(len(rows), 1))
            self.progress_bar.setValue(len(rows))
            self.status.setText(f"Done: {len(rows)} row(s)")

        @QtCore.Slot(object)
        def _show_result(self, row: MeasurementRow) -> None:
            self.viewer.set_result(row, self._request, align_camera=True)

        @QtCore.Slot(int, int, str)
        def _on_progress(self, index: int, total: int, description: str) -> None:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(index)
            self.status.setText(f"Sweep {index}/{total}: {description}")
            self.controls.set_operation_message(f"Sweep {index:,} of {total:,} · {description}")

        @QtCore.Slot(object)
        def _on_state_changed(self, state: OperationState) -> None:
            self.controls.set_busy(state)
            self.results.set_busy(state is not OperationState.IDLE)
            if state is OperationState.LOADING:
                self.progress_bar.setRange(0, 0)
                self.status.setText("Loading model")
            elif state is OperationState.CALCULATING:
                self.progress_bar.setRange(0, 0)
                self.status.setText("Calculating")
            elif state is OperationState.CANCELLING:
                self.status.setText("Cancelling")
            elif state is OperationState.IDLE and self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 1)
                self.progress_bar.setValue(0)

        @QtCore.Slot(bool)
        def _set_base_face_available(self, available: bool) -> None:
            self.controls.show_base_face.setEnabled(available)
            self.controls.show_base_face.setToolTip(
                "Highlight the Xmax base face." if available else "No Xmax base face found."
            )
            if not available:
                self.controls.show_base_face.setChecked(False)

        @QtCore.Slot(bool)
        def _set_newly_exposed_surface_available(self, available: bool) -> None:
            self.controls.show_newly_exposed_surface.setEnabled(available)
            self.controls.show_newly_exposed_surface.setToolTip(
                "Highlight surfaces newly exposed by subtraction."
                if available
                else "No newly exposed subtraction surfaces found."
            )

        def _show_documentation(self) -> None:
            if self._documentation_index is None:
                try:
                    self._documentation_index, self._documentation_tempdir = (
                        _documentation_site_index(self._documentation_resources)
                    )
                except Exception as exc:
                    self._show_error(str(exc))
                    return
            url = QtCore.QUrl.fromLocalFile(str(self._documentation_index))
            if not QtGui.QDesktopServices.openUrl(url):
                self._show_error("Could not open the documentation site in the default browser.")

        @QtCore.Slot(str)
        def _show_error(self, message: str) -> None:
            self.status.setText(f"Error: {message}")
            QtWidgets.QMessageBox.critical(self, "cadmetrics error", message)

        def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
            if self.controller.state is not OperationState.IDLE:
                self._close_when_idle = True
                self.controller.shutdown()
                event.ignore()
                return
            self._documentation_resources.close()
            event.accept()

        @QtCore.Slot()
        def _finish_close(self) -> None:
            if self._close_when_idle:
                self._close_when_idle = False
                self.close()


else:
    MainWindow = object  # type: ignore[misc,assignment]


def _documentation_site_index(
    stack: ExitStack,
) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    source_file = Path(__file__).resolve()
    for parent in source_file.parents:
        if (parent / "README.md").is_file() and (parent / "docs").is_dir():
            temporary = tempfile.TemporaryDirectory(prefix="cadmetrics-docs-")
            site_dir = Path(temporary.name) / "site"
            build_documentation_site(parent, site_dir)
            return site_dir / "index.html", temporary

    packaged = resources.files("cadmetrics").joinpath("_docs_site")
    try:
        site_dir = stack.enter_context(resources.as_file(packaged))
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise RuntimeError("Bundled cadmetrics documentation site was not found.") from exc
    index = Path(site_dir) / "index.html"
    if not index.is_file():
        raise RuntimeError("Bundled cadmetrics documentation index was not found.")
    return index, None
