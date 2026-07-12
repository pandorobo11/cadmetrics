from __future__ import annotations

from threading import Event

from cadmetrics.api import inspect_model
from cadmetrics.gui.jobs import CalculationRequest, run_calculation
from cadmetrics.types import ModelData

try:
    from PySide6 import QtCore
except ImportError:  # pragma: no cover - optional GUI dependency
    QtCore = None


class CancelledCalculation(Exception):
    pass


if QtCore is not None:

    class CalculationWorker(QtCore.QObject):
        model_loaded = QtCore.Signal(object)
        load_finished = QtCore.Signal()
        finished = QtCore.Signal(list)
        failed = QtCore.Signal(str)
        progress = QtCore.Signal(int, int, str)
        cancelled = QtCore.Signal()

        def __init__(self, request: CalculationRequest, *, calculate: bool) -> None:
            super().__init__()
            self._request = request
            self._calculate = calculate
            self._cancel = Event()

        @QtCore.Slot()
        def run(self) -> None:
            try:
                model = self._load_model()
                self._raise_if_cancelled()
                self.model_loaded.emit(model)
                if not self._calculate:
                    self.load_finished.emit()
                    return
                rows = run_calculation(
                    self._request,
                    model=model,
                    progress_callback=self._on_progress,
                )
            except CancelledCalculation:
                self.cancelled.emit()
                return
            except Exception as exc:
                self.failed.emit(str(exc))
                return
            self.finished.emit(rows)

        def cancel(self) -> None:
            self._cancel.set()

        def _load_model(self) -> ModelData:
            request = self._request
            return inspect_model(
                request.file,
                input_unit=request.input_unit,
                output_unit=request.output_unit,
                mesh_deflection=request.mesh_deflection,
                angular_deflection=request.angular_deflection,
                base_tolerance=request.base_tolerance,
                step_metric_source=request.step_metric_source,
                axis_map=request.axis_map,
                step_components=request.step_components,
            )

        def _raise_if_cancelled(self) -> None:
            if self._cancel.is_set():
                raise CancelledCalculation

        def _on_progress(self, index: int, total: int, description: str) -> None:
            self._raise_if_cancelled()
            self.progress.emit(index, total, description)


else:
    CalculationWorker = object  # type: ignore[misc,assignment]
