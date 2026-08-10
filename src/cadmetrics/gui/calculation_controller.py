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
        cancel_event: Event | None = None,
    ) -> None:
        super().__init__()
        self._request = request
        self._model = model
        self._calculate = calculate
        self._cancel = cancel_event or Event()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            model = self._model
            if model is None:
                model = load_model_for_request(self._request)
                self._raise_if_cancelled()
                self.model_loaded.emit(model)
            elif not self._calculate:
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
                cancel_callback=self._raise_if_cancelled,
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


class _OperationContext(QtCore.QObject):
    """Own one worker operation until both native QObjects are deleted."""

    teardown_complete = QtCore.Signal()

    def __init__(
        self,
        request: CalculationRequest,
        *,
        model: ModelData | None,
        calculate: bool,
        parent: QtCore.QObject,
    ) -> None:
        super().__init__(parent)
        self.cancel_event = Event()
        self.operation_thread = QtCore.QThread(self)
        self.worker = _OperationWorker(
            request,
            model=model,
            calculate=calculate,
            cancel_event=self.cancel_event,
        )
        self.worker.moveToThread(self.operation_thread)
        self._thread_finished = False
        self._worker_destroyed = False
        self._thread_deletion_requested = False

        self.operation_thread.finished.connect(self.worker.deleteLater)
        self.operation_thread.finished.connect(
            self._on_thread_finished,
            QtCore.Qt.ConnectionType.QueuedConnection,
        )
        self.worker.destroyed.connect(
            self._on_worker_destroyed,
            QtCore.Qt.ConnectionType.QueuedConnection,
        )
        self.operation_thread.destroyed.connect(
            self._on_thread_destroyed,
            QtCore.Qt.ConnectionType.QueuedConnection,
        )

    def cancel(self) -> None:
        self.cancel_event.set()

    @QtCore.Slot()
    def _on_thread_finished(self) -> None:
        self._thread_finished = True
        self._delete_thread_when_safe()

    @QtCore.Slot()
    def _on_worker_destroyed(self) -> None:
        self._worker_destroyed = True
        self._delete_thread_when_safe()

    def _delete_thread_when_safe(self) -> None:
        if (
            not self._thread_finished
            or not self._worker_destroyed
            or self._thread_deletion_requested
        ):
            return
        self._thread_deletion_requested = True
        self.operation_thread.deleteLater()

    @QtCore.Slot()
    def _on_thread_destroyed(self) -> None:
        self.teardown_complete.emit()


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
        self._operation: _OperationContext | None = None
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
        if self._operation is None or self._state is not OperationState.CALCULATING:
            return
        self._set_state(OperationState.CANCELLING)
        self._operation.cancel()

    def shutdown(self) -> None:
        if self._operation is None:
            self.shutdown_ready.emit()
            return
        self._shutdown_requested = True
        if self._state is OperationState.CALCULATING:
            self.cancel()
        else:
            self._set_state(OperationState.CANCELLING)
            self._operation.cancel()

    def _start(self, request: CalculationRequest, *, calculate: bool) -> None:
        if self._thread is not None:
            self.message.emit("Another model operation is already running.")
            return
        try:
            if calculate:
                request.resolved_attitude()
            key = model_load_key(request)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        cached_model = self._model if self._model_key == key else None
        self._pending_key = key
        self._set_state(
            OperationState.CALCULATING if cached_model is not None and calculate else OperationState.LOADING
        )
        operation = _OperationContext(
            request,
            model=cached_model,
            calculate=calculate,
            parent=self,
        )
        self._operation = operation
        self._thread = operation.operation_thread
        self._worker = operation.worker
        operation.operation_thread.started.connect(operation.worker.run)
        operation.worker.model_loaded.connect(self._on_model_loaded)
        operation.worker.calculating.connect(
            self._on_calculating,
            QtCore.Qt.ConnectionType.QueuedConnection,
        )
        operation.worker.results_ready.connect(self.results_ready)
        operation.worker.progress.connect(self.progress)
        operation.worker.failed.connect(self.failed)
        operation.worker.cancelled.connect(self.cancelled)
        for terminal in (
            operation.worker.results_ready,
            operation.worker.load_finished,
            operation.worker.failed,
            operation.worker.cancelled,
        ):
            terminal.connect(operation.operation_thread.quit)
        operation.teardown_complete.connect(self._on_operation_torn_down)
        operation.operation_thread.start()

    @QtCore.Slot()
    def _on_calculating(self) -> None:
        self._set_state(OperationState.CALCULATING)

    @QtCore.Slot(object)
    def _on_model_loaded(self, model: ModelData) -> None:
        self._model = model
        self._model_key = self._pending_key
        self.model_loaded.emit(model)

    @QtCore.Slot()
    def _on_operation_torn_down(self) -> None:
        operation = self._operation
        if operation is None:
            return
        self._operation = None
        self._thread = None
        self._worker = None
        self._pending_key = None
        operation.deleteLater()
        self._set_state(OperationState.IDLE)
        if self._shutdown_requested:
            self._shutdown_requested = False
            self.shutdown_ready.emit()

    def _set_state(self, state: OperationState) -> None:
        if state == self._state:
            return
        self._state = state
        self.state_changed.emit(state)
