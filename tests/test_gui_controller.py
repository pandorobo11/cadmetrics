from __future__ import annotations

from pathlib import Path
from threading import Event

import numpy as np
import pytest

pytest.importorskip("PySide6")

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


def test_controller_rejects_overlapping_operation(qtbot, monkeypatch) -> None:
    release = Event()

    def slow_load(request):
        release.wait(timeout=2)
        return _model()

    monkeypatch.setattr(
        "cadmetrics.gui.calculation_controller.load_model_for_request",
        slow_load,
    )
    controller = CalculationController()
    messages = []
    controller.message.connect(messages.append)
    request = CalculationRequest(file=Path("model.step"))

    controller.load_only(request)
    controller.calculate(request)
    release.set()
    qtbot.waitUntil(lambda: controller.state is OperationState.IDLE)

    assert messages == ["Another model operation is already running."]


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
