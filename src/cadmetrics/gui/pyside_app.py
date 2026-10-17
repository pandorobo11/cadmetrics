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

    MODEL_FILE_SUFFIXES = frozenset({".stl", ".step", ".stp"})

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("cadmetrics")
            self.setAcceptDrops(True)
            # Current inputs, and the inputs that produced the rows in the results panel.
            self._request: CalculationRequest | None = None
            self._results_request: CalculationRequest | None = None
            self._calculation_running = False
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
            file_menu = self.menuBar().addMenu("File")
            self.open_action = QtGui.QAction("Open…", self)
            self.open_action.setShortcut(QtGui.QKeySequence.StandardKey.Open)
            self.open_action.triggered.connect(self._open_file)
            self.run_action = QtGui.QAction("Run Sweep", self)
            # Qt maps Ctrl to Command on macOS.
            self.run_action.setShortcut(QtGui.QKeySequence("Ctrl+R"))
            self.run_action.triggered.connect(self._run_sweep)
            self.save_csv_action = QtGui.QAction("Save CSV…", self)
            self.save_csv_action.setShortcut(QtGui.QKeySequence.StandardKey.Save)
            self.save_csv_action.triggered.connect(self._save_csv)
            self.cancel_action = QtGui.QAction("Cancel", self)
            self.cancel_action.setShortcut(QtGui.QKeySequence("Ctrl+."))
            self.cancel_action.triggered.connect(self.controller.cancel)
            file_menu.addAction(self.open_action)
            file_menu.addSeparator()
            file_menu.addAction(self.run_action)
            file_menu.addAction(self.cancel_action)
            file_menu.addSeparator()
            file_menu.addAction(self.save_csv_action)

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
            self.controls.error.connect(self._show_error)
            self.controls.save_image_button.clicked.connect(self.viewer.choose_and_save_image)
            self.viewer.base_face_available.connect(self._set_base_face_available)
            self.viewer.newly_exposed_surface_available.connect(
                self._set_newly_exposed_surface_available
            )
            self.viewer.error.connect(self._show_error)
            self.viewer.message.connect(self.status.setText)
            self.results.selected_row_changed.connect(self._show_result)
            self.results.rows_changed.connect(self._sync_actions)
            self.results.error.connect(self._show_error)
            self.controller.model_loaded.connect(self._on_model_loaded)
            self.controller.rows_appended.connect(self._on_rows_appended)
            self.controller.results_ready.connect(self._on_results_ready)
            self.controller.progress.connect(self._on_progress)
            self.controller.state_changed.connect(self._on_state_changed)
            self.controller.failed.connect(self._on_failed)
            self.controller.cancelled.connect(self._on_cancelled)
            self.controller.message.connect(self.status.setText)
            self.controller.shutdown_ready.connect(self._finish_close)

        @QtCore.Slot(object)
        def _calculate(self, request: CalculationRequest) -> None:
            self._request = request
            self._invalidate_results()
            self._results_request = request
            self.results.set_protected_paths(_request_paths(request))
            self.viewer.set_request(request)
            self._calculation_running = True
            self.controller.calculate(request)

        @QtCore.Slot(object)
        def _load_model(self, request: CalculationRequest) -> None:
            self._request = request
            self._invalidate_results()
            self.viewer.set_request(request)
            self.controller.load_only(request)

        @QtCore.Slot(object)
        def _preview_request(self, request: CalculationRequest | None) -> None:
            if request != self._request:
                self._request = request
                self._sync_stale_results()
            self.viewer.set_request(request)

        @QtCore.Slot(object)
        def _on_model_loaded(self, model: ModelData) -> None:
            self.controls.set_model(model)
            self.viewer.set_model(model)
            self.viewer.set_request(self._request)
            self.status.setText("Model loaded")

        @QtCore.Slot(list)
        def _on_rows_appended(self, rows: list[MeasurementRow]) -> None:
            self.results.append_rows(rows)

        @QtCore.Slot(list)
        def _on_results_ready(self, rows: list[MeasurementRow]) -> None:
            self._calculation_running = False
            if self._results_request is None:
                self._results_request = self._request
            protected_paths = (
                _request_paths(self._results_request) if self._results_request is not None else ()
            )
            streamed = self.results.rows
            if len(streamed) != len(rows) or any(
                left is not right for left, right in zip(streamed, rows, strict=True)
            ):
                self.results.set_rows(rows, protected_paths=protected_paths)
            else:
                self.results.set_protected_paths(protected_paths)
            if not self.results.has_selection():
                self.results.select_last_row()
            self.progress_bar.setRange(0, max(len(rows), 1))
            self.progress_bar.setValue(len(rows))
            self.status.setText(f"Done: {len(rows):,} row(s)")
            # Inputs edited while the sweep was running make the new rows stale at once.
            self._sync_stale_results()

        @QtCore.Slot()
        def _on_cancelled(self) -> None:
            self._calculation_running = False
            count = len(self.results.rows)
            self.status.setText(
                f"Cancelled: kept {count:,} completed row(s)" if count else "Cancelled"
            )
            self._sync_stale_results()

        @QtCore.Slot(str)
        def _on_failed(self, message: str) -> None:
            self._calculation_running = False
            self._show_error(message)

        @QtCore.Slot(object)
        def _show_result(self, row: MeasurementRow) -> None:
            # Rows always render with the request that produced them, even when stale.
            self.viewer.set_result(row, self._results_request, align_camera=True)

        @QtCore.Slot(int, int, str)
        def _on_progress(self, index: int, total: int, description: str) -> None:
            # Progress text lives next to Cancel in the action bar; the status bar keeps
            # only the progress bar so the same message is not shown twice.
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(index)
            self.controls.set_operation_message(f"Sweep {index:,} of {total:,} · {description}")

        @QtCore.Slot(object)
        def _on_state_changed(self, state: OperationState) -> None:
            self.controls.set_busy(state)
            busy = state is not OperationState.IDLE
            loading_only = state is OperationState.LOADING and not self._calculation_running
            self.results.set_busy(busy, title="Loading model…" if loading_only else "Calculating…")
            if state is OperationState.LOADING:
                self.progress_bar.setRange(0, 0)
                self.status.setText("Loading model")
            elif state is OperationState.CALCULATING:
                self.progress_bar.setRange(0, 0)
                self.status.setText("Calculating")
            elif state is OperationState.CANCELLING:
                self.status.setText("Finishing the current geometry operation")
            elif state is OperationState.IDLE:
                self._calculation_running = False
                if self.progress_bar.maximum() == 0:
                    self.progress_bar.setRange(0, 1)
                    self.progress_bar.setValue(0)
            self._sync_actions()

        @QtCore.Slot()
        def _sync_actions(self) -> None:
            idle = self.controller.state is OperationState.IDLE
            self.open_action.setEnabled(idle)
            self.run_action.setEnabled(idle)
            self.cancel_action.setEnabled(self.controller.state is OperationState.CALCULATING)
            self.save_csv_action.setEnabled(self.results.can_save)

        def _open_file(self) -> None:
            if self.controls.browse_button.isEnabled():
                self.controls.browse_button.click()

        def _run_sweep(self) -> None:
            if self.controls.run_button.isEnabled():
                self.controls.run_button.click()

        def _save_csv(self) -> None:
            if self.results.can_save:
                self.results.choose_csv_path()

        def load_dropped_files(self, paths: tuple[Path, ...]) -> bool:
            if not paths or self.controller.state is not OperationState.IDLE:
                return False
            self.controls.set_file_paths(paths)
            # ControlPanel has no public "load these files" API, and control_panel.py is
            # owned elsewhere. Reuse the exact steps of its Browse handler: reset the
            # component filter for the new files, then emit model_reload_requested.
            self.controls._clear_components()
            self.controls._apply_advanced_settings()
            return True

        def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # noqa: N802
            self._accept_model_drag(event)

        def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:  # noqa: N802
            self._accept_model_drag(event)

        def _accept_model_drag(self, event: QtGui.QDragMoveEvent) -> None:
            if _dropped_model_paths(event.mimeData()) and (
                self.controller.state is OperationState.IDLE
            ):
                event.acceptProposedAction()
            else:
                event.ignore()

        def dropEvent(self, event: QtGui.QDropEvent) -> None:  # noqa: N802
            if self.load_dropped_files(_dropped_model_paths(event.mimeData())):
                event.acceptProposedAction()
            else:
                event.ignore()

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

        def _invalidate_results(self) -> None:
            self.results.clear()
            self._results_request = None
            self.viewer.set_result(None, self._request)
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)

        def _sync_stale_results(self) -> None:
            if self._calculation_running or not self.results.rows:
                return
            stale = self._request != self._results_request
            was_stale = self.results.is_stale
            self.results.mark_stale(stale)
            if stale and not was_stale:
                # The preview follows the edited inputs; stale rows re-render with their
                # own request only when the user selects one.
                self.viewer.set_result(None, self._request)
                self.status.setText("Inputs changed: results are out of date")
            elif was_stale and not stale:
                self.status.setText(f"Inputs match the results: {len(self.results.rows):,} row(s)")

        def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
            if self.controller.state is not OperationState.IDLE:
                self._close_when_idle = True
                previous_state = self.controller.state
                self.controller.shutdown()
                if previous_state is OperationState.LOADING:
                    self.status.setText(
                        "Waiting for the current geometry operation to finish before exit"
                    )
                else:
                    self.status.setText("Stopping after the current sweep case before exit")
                event.ignore()
                return
            self._documentation_resources.close()
            event.accept()

        @QtCore.Slot()
        def _finish_close(self) -> None:
            if self._close_when_idle:
                self._close_when_idle = False
                self.close()

    def _request_paths(request: CalculationRequest) -> tuple[Path, ...]:
        return request.file if isinstance(request.file, tuple) else (request.file,)

    def _dropped_model_paths(mime_data: QtCore.QMimeData | None) -> tuple[Path, ...]:
        if mime_data is None or not mime_data.hasUrls():
            return ()
        paths = tuple(Path(url.toLocalFile()) for url in mime_data.urls() if url.isLocalFile())
        if not paths or any(path.suffix.lower() not in MODEL_FILE_SUFFIXES for path in paths):
            return ()
        return paths

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


if __name__ == "__main__":
    main()
