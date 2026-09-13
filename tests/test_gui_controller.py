from __future__ import annotations

from dataclasses import replace
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


def test_controller_reuses_model_until_geometry_changes_on_its_own_thread(
    qtbot, monkeypatch
) -> None:
    loads = []
    models = []
    calculations = []
    row = _row()

    def fake_load(request):
        model = _model()
        loads.append(request)
        models.append(model)
        return model

    def fake_calculate(request, *, model, progress_callback, cancel_callback):
        calculations.append((request, model))
        return [row]

    monkeypatch.setattr("cadmetrics.gui.calculation_controller.load_model_for_request", fake_load)
    monkeypatch.setattr("cadmetrics.gui.calculation_controller.run_calculation", fake_calculate)
    controller = CalculationController()
    controller_thread_id = get_ident()
    transitions = []
    controller.state_changed.connect(
        lambda state: transitions.append((state, get_ident())),
        QtCore.Qt.ConnectionType.DirectConnection,
    )
    request = CalculationRequest(file=Path("model.step"))
    changed_attitude = replace(request, alpha_start=25.0, alpha_end=25.0, beta_end=10.0)
    changed_axis = replace(changed_attitude, axis_map="-x,y,z")
    changed_component_mode = replace(changed_axis, step_component_mode="subtract")
    loaded = []
    results = []
    controller.model_loaded.connect(loaded.append)
    controller.results_ready.connect(results.append)

    controller.load_only(request)
    qtbot.waitUntil(lambda: controller.state is OperationState.IDLE)
    for calculation_request in (changed_attitude, changed_axis, changed_component_mode):
        controller.calculate(calculation_request)
        qtbot.waitUntil(lambda: controller.state is OperationState.IDLE)

    assert loads == [request, changed_axis, changed_component_mode]
    assert all(actual is expected for actual, expected in zip(loaded, models, strict=True))
    assert [request for request, _ in calculations] == [
        changed_attitude,
        changed_axis,
        changed_component_mode,
    ]
    assert all(
        actual is expected for (_, actual), expected in zip(calculations, models, strict=True)
    )
    assert results == [[row], [row], [row]]
    assert {state for state, _ in transitions} == {
        OperationState.LOADING,
        OperationState.CALCULATING,
        OperationState.IDLE,
    }
    assert {thread_id for _, thread_id in transitions} == {controller_thread_id}


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


def test_controller_rejects_overlap_and_waits_for_cancelled_worker_on_shutdown(
    qtbot, monkeypatch
) -> None:
    started = Event()
    release = Event()
    calculations = []

    def fake_calculate(request, *, model, progress_callback, cancel_callback):
        calculations.append(request)
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
    messages = []
    results = []
    controller.cancelled.connect(lambda: cancelled.append(True))
    controller.shutdown_ready.connect(lambda: shutdown.append(True))
    controller.message.connect(messages.append)
    controller.results_ready.connect(results.append)
    request = CalculationRequest(file=Path("model.step"))

    controller.calculate(request)
    try:
        qtbot.waitUntil(lambda: started.is_set() and controller.state is OperationState.CALCULATING)
        controller.calculate(request)
        assert messages and "already running" in messages[-1]
        controller.shutdown()
        assert controller.state is OperationState.CANCELLING
        assert not shutdown
    finally:
        release.set()
    qtbot.waitUntil(lambda: bool(shutdown))

    assert calculations == [request]
    assert cancelled == [True]
    assert results == []
    assert controller.state is OperationState.IDLE


def test_controller_repeated_operations_finish_native_teardown(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        "cadmetrics.gui.calculation_controller.load_model_for_request", lambda request: _model()
    )
    controller = CalculationController()
    request = CalculationRequest(file=Path("model.step"))

    for _ in range(2):
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
