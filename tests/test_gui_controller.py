from __future__ import annotations

from pathlib import Path
from threading import Event, get_ident

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6 import QtCore

from cadmetrics.gui.calculation_controller import CalculationController
from cadmetrics.gui.gui_types import OperationState
from cadmetrics.gui.jobs import CalculationRequest
from cadmetrics.types import MeasurementRow, ModelData


def test_controller_loads_then_reuses_model(qtbot, monkeypatch) -> None:
    loads = []
    calculations = []
    model = _model()
    row = _row()

    def fake_load(request):
        loads.append(request)
        return model

    def fake_calculate(request, *, model, progress_callback, cancel_callback):
        calculations.append((request, model))
        cancel_callback()
        return [row]

    monkeypatch.setattr("cadmetrics.gui.calculation_controller.load_model_for_request", fake_load)
    monkeypatch.setattr("cadmetrics.gui.calculation_controller.run_calculation", fake_calculate)
    controller = CalculationController()
    request = CalculationRequest(file=Path("model.step"))
    loaded = []
    results = []
    controller.model_loaded.connect(loaded.append)
    controller.results_ready.connect(results.append)

    controller.load_only(request)
    qtbot.waitUntil(lambda: controller.state is OperationState.IDLE)
    controller.calculate(request)
    qtbot.waitUntil(lambda: controller.state is OperationState.IDLE)

    assert loads == [request]
    assert loaded == [model]
    assert calculations == [(request, model)]
    assert results == [[row]]


def test_controller_reloads_when_geometry_settings_change(qtbot, monkeypatch) -> None:
    loads = []
    monkeypatch.setattr(
        "cadmetrics.gui.calculation_controller.load_model_for_request",
        lambda request: loads.append(request) or _model(),
    )
    controller = CalculationController()

    controller.load_only(CalculationRequest(file=Path("model.step")))
    qtbot.waitUntil(lambda: controller.state is OperationState.IDLE)
    controller.load_only(
        CalculationRequest(file=Path("model.step"), axis_map="-x,y,z")
    )
    qtbot.waitUntil(lambda: controller.state is OperationState.IDLE)

    assert len(loads) == 2


def test_controller_rejects_overlapping_operation() -> None:
    controller = CalculationController()
    messages = []
    controller.message.connect(messages.append)
    request = CalculationRequest(file=Path("model.step"))
    active_thread = QtCore.QThread(controller)

    controller._thread = active_thread
    try:
        controller.calculate(request)
    finally:
        controller._thread = None

    assert messages == ["Another model operation is already running."]


@pytest.mark.parametrize(
    ("calculation_request", "message"),
    [
        (
            CalculationRequest(
                file=Path("model.step"),
                attitude_mode="vector",
                vector_x=0.0,
                vector_y=0.0,
                vector_z=0.0,
            ),
            "greater than zero",
        ),
        (
            CalculationRequest(file=Path("model.step"), base_tolerance=0.0),
            "base_tolerance must be greater than zero",
        ),
        (
            CalculationRequest(file=Path("model.step"), axis_map="x,x,z"),
            "axis_map must use each source axis exactly once",
        ),
    ],
)
def test_controller_reports_invalid_request_without_starting_worker(
    calculation_request: CalculationRequest,
    message: str,
) -> None:
    controller = CalculationController()
    failures = []
    controller.failed.connect(failures.append)

    controller.calculate(calculation_request)

    assert failures and message in failures[0]
    assert controller.state is OperationState.IDLE
    assert controller._operation is None


def test_controller_cancel_and_shutdown_wait_for_worker(qtbot, monkeypatch) -> None:
    started = Event()
    release = Event()

    def fake_calculate(request, *, model, progress_callback, cancel_callback):
        started.set()
        release.wait(timeout=2)
        cancel_callback()
        progress_callback(1, 1, "done")
        return [_row()]

    monkeypatch.setattr(
        "cadmetrics.gui.calculation_controller.load_model_for_request", lambda request: _model()
    )
    monkeypatch.setattr("cadmetrics.gui.calculation_controller.run_calculation", fake_calculate)
    controller = CalculationController()
    cancelled = []
    shutdown = []
    controller.cancelled.connect(lambda: cancelled.append(True))
    controller.shutdown_ready.connect(lambda: shutdown.append(True))

    controller.calculate(CalculationRequest(file=Path("model.step")))
    qtbot.waitUntil(started.is_set)
    controller.shutdown()
    assert controller.state is OperationState.CANCELLING
    release.set()
    qtbot.waitUntil(lambda: bool(shutdown))

    assert cancelled == [True]
    assert controller.state is OperationState.IDLE


def test_controller_state_transitions_stay_on_controller_thread(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        "cadmetrics.gui.calculation_controller.load_model_for_request", lambda request: _model()
    )
    monkeypatch.setattr(
        "cadmetrics.gui.calculation_controller.run_calculation",
        lambda request, *, model, progress_callback, cancel_callback: [_row()],
    )
    controller = CalculationController()
    controller_thread_id = get_ident()
    transition_thread_ids = []
    original_set_state = controller._set_state

    def record_set_state(state: OperationState) -> None:
        transition_thread_ids.append(get_ident())
        original_set_state(state)

    monkeypatch.setattr(controller, "_set_state", record_set_state)

    controller.calculate(CalculationRequest(file=Path("model.step")))
    qtbot.waitUntil(lambda: controller.state is OperationState.IDLE)

    assert len(transition_thread_ids) == 3
    assert set(transition_thread_ids) == {controller_thread_id}


def test_controller_repeated_operations_finish_native_teardown(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        "cadmetrics.gui.calculation_controller.load_model_for_request", lambda request: _model()
    )
    controller = CalculationController()
    request = CalculationRequest(file=Path("model.step"))

    for _ in range(100):
        destroyed = {"worker": False, "thread": False}
        controller.load_only(request)
        operation = controller._operation
        assert operation is not None
        operation.worker.destroyed.connect(
            lambda *_args, flags=destroyed: flags.__setitem__("worker", True)
        )
        operation.operation_thread.destroyed.connect(
            lambda *_args, flags=destroyed: flags.__setitem__("thread", True)
        )

        qtbot.waitUntil(lambda: controller.state is OperationState.IDLE)

        assert destroyed == {"worker": True, "thread": True}
        assert controller._operation is None
        assert controller._worker is None
        assert controller._thread is None


def _model() -> ModelData:
    return ModelData(
        path=Path("model.step"),
        source_format="step",
        vertices=np.empty((0, 3), dtype=float),
        faces=np.empty((0, 3), dtype=np.int64),
        input_unit="m",
        output_unit="m",
        volume=1.0,
        surface_area=6.0,
        base_area=1.0,
        is_watertight=True,
    )


def _row() -> MeasurementRow:
    return MeasurementRow(
        file="model.step",
        input_unit="m",
        output_unit="m",
        roll_deg=0.0,
        alpha_deg=0.0,
        beta_deg=0.0,
        volume=1.0,
        surface_area=6.0,
        projected_area=1.0,
        is_watertight=True,
    )
