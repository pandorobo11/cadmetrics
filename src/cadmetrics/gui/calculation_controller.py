from __future__ import annotations

from threading import Event

from PySide6 import QtCore

from cadmetrics.gui.gui_types import ModelLoadKey, OperationState
from cadmetrics.gui.jobs import CalculationRequest, run_calculation
from cadmetrics.gui.model_loading import load_model_for_request, model_load_key
from cadmetrics.types import ModelData


class CancelledOperation(Exception):
    pass


class _OperationWorker(QtCore.QObject):
    model_loaded = QtCore.Signal(object)
    calculating = QtCore.Signal()
    results_ready = QtCore.Signal(list)
    load_finished = QtCore.Signal()
    progress = QtCore.Signal(int, int, str)
    failed = QtCore.Signal(str)
    cancelled = QtCore.Signal()

    def __init__(
        self,
        request: CalculationRequest,
        *,
        model: ModelData | None,
        calculate: bool,
    ) -> None:
        super().__init__()
        self._request = request
        self._model = model
        self._calculate = calculate
        self._cancel = Event()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            model = self._model
            if model is None:
                model = load_model_for_request(self._request)
                self._raise_if_cancelled()
                self.model_loaded.emit(model)
            if not self._calculate:
                self.load_finished.emit()
                return
            self._raise_if_cancelled()
            self.calculating.emit()
            rows = run_calculation(
                self._request,
                model=model,
                progress_callback=self._on_progress,
            )
        except CancelledOperation:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.results_ready.emit(rows)

    def cancel(self) -> None:
        self._cancel.set()

    def _raise_if_cancelled(self) -> None:
        if self._cancel.is_set():
            raise CancelledOperation

    def _on_progress(self, index: int, total: int, description: str) -> None:
        self._raise_if_cancelled()
        self.progress.emit(index, total, description)


class CalculationController(QtCore.QObject):
    model_loaded = QtCore.Signal(object)
    results_ready = QtCore.Signal(list)
    progress = QtCore.Signal(int, int, str)
    state_changed = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    cancelled = QtCore.Signal()
    message = QtCore.Signal(str)
    shutdown_ready = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._state = OperationState.IDLE
        self._thread: QtCore.QThread | None = None
        self._worker: _OperationWorker | None = None
        self._model: ModelData | None = None
        self._model_key: ModelLoadKey | None = None
        self._pending_key: ModelLoadKey | None = None
        self._shutdown_requested = False

    @property
    def state(self) -> OperationState:
        return self._state

    @property
    def model(self) -> ModelData | None:
        return self._model

    def load_only(self, request: CalculationRequest) -> None:
        self._start(request, calculate=False)

    def calculate(self, request: CalculationRequest) -> None:
        self._start(request, calculate=True)

    def cancel(self) -> None:
        if self._worker is None:
            return
        self._set_state(OperationState.CANCELLING)
        self._worker.cancel()

    def shutdown(self) -> None:
        if self._thread is None:
            self.shutdown_ready.emit()
            return
        self._shutdown_requested = True
        self.cancel()

    def _start(self, request: CalculationRequest, *, calculate: bool) -> None:
        if self._thread is not None:
            self.message.emit("Another model operation is already running.")
            return
        key = model_load_key(request)
        cached_model = self._model if self._model_key == key else None
        self._pending_key = key
        self._set_state(
            OperationState.CALCULATING if cached_model is not None and calculate else OperationState.LOADING
        )
        self._thread = QtCore.QThread(self)
        self._worker = _OperationWorker(request, model=cached_model, calculate=calculate)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.model_loaded.connect(self._on_model_loaded)
        self._worker.calculating.connect(lambda: self._set_state(OperationState.CALCULATING))
        self._worker.results_ready.connect(self.results_ready)
        self._worker.progress.connect(self.progress)
        self._worker.failed.connect(self.failed)
        self._worker.cancelled.connect(self.cancelled)
        for terminal in (
            self._worker.results_ready,
            self._worker.load_finished,
            self._worker.failed,
            self._worker.cancelled,
        ):
            terminal.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    @QtCore.Slot(object)
    def _on_model_loaded(self, model: ModelData) -> None:
        self._model = model
        self._model_key = self._pending_key
        self.model_loaded.emit(model)

    @QtCore.Slot()
    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._pending_key = None
        self._set_state(OperationState.IDLE)
        if self._shutdown_requested:
            self._shutdown_requested = False
            self.shutdown_ready.emit()

    def _set_state(self, state: OperationState) -> None:
        if state == self._state:
            return
        self._state = state
        self.state_changed.emit(state)
