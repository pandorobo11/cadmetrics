from __future__ import annotations

import importlib.util
import threading
import time
from dataclasses import fields, replace
from pathlib import Path

import numpy as np
import pytest

import cadmetrics.api as api
from cadmetrics.api import inspect_model, sweep_model
from cadmetrics.attitude import resolve_sweep_attitude
from cadmetrics.orientation import Orientation, projection_direction_for_orientation
from cadmetrics.projection import projected_metrics


ROOT = Path(__file__).resolve().parents[1]
HAS_OCP = importlib.util.find_spec("OCP") is not None
# alpha 0/360, the beta = +-90 poles and alpha/alpha+180 at beta 0 all repeat a
# direction or its reverse, so this sweep exercises reuse heavily.
SWEEP = {
    "attitude": "alpha-beta",
    "roll_deg": 0.0,
    "alpha_deg": "0:360:45",
    "beta_deg": "-90:90:45",
}
ROLL_SWEEP = {
    "attitude": "roll-pitch",
    "roll_deg": "0:360:90",
    "pitch_deg": "-90:90:45",
}
SAMPLE_PATHS = [
    pytest.param(ROOT / "samples/frame_with_hole/frame_with_hole_binary.stl", id="frame-stl"),
    pytest.param(
        ROOT / "samples/two_boxes_overlap_projection/two_boxes_overlap_projection.step",
        id="two-boxes-step",
        marks=pytest.mark.skipif(not HAS_OCP, reason="requires cadmetrics[step]"),
    ),
]


def _offset_model(path: Path):
    model = inspect_model(path)
    # Move the model away from the origin so centroid re-projection is exercised.
    return replace(model, vertices=model.vertices + np.array([0.7, -1.3, 2.1]))


def _sweep(model, attitude, *, max_workers, reuse_directions, **kwargs):
    resolved = resolve_sweep_attitude(**attitude)
    return api._sweep_model_with_attitude(
        model,
        resolved,
        max_workers=max_workers,
        reuse_directions=reuse_directions,
        **kwargs,
    )


def _assert_rows_match(rows, expected) -> None:
    assert len(rows) == len(expected)
    approx_fields = {
        "projected_area",
        "centroid_u",
        "centroid_v",
        "centroid_x",
        "centroid_y",
        "centroid_z",
    }
    for row, baseline in zip(rows, expected, strict=True):
        for field in fields(row):
            name = field.name
            if name == "elapsed_sec":
                continue
            value = getattr(row, name)
            expected_value = getattr(baseline, name)
            if name in approx_fields and expected_value is not None:
                assert value == pytest.approx(expected_value, rel=1e-9, abs=1e-9), name
            else:
                assert value == expected_value, name


@pytest.mark.parametrize("path", SAMPLE_PATHS)
@pytest.mark.parametrize("attitude", [SWEEP, ROLL_SWEEP], ids=["alpha-beta", "roll-pitch"])
def test_reuse_and_parallel_sweeps_match_serial_rows(path: Path, attitude) -> None:
    if not path.exists():
        pytest.skip(f"missing sample {path}")
    model = _offset_model(path)
    baseline = _sweep(model, attitude, max_workers=1, reuse_directions=False)

    # The serial, no-reuse sweep is the original per-orientation calculation.
    for row, orientation in zip(baseline, _orientations(attitude), strict=True):
        assert row.projected_area == projected_metrics(model, orientation=orientation).area

    for max_workers, reuse in [(1, True), (4, False), (4, True)]:
        rows = _sweep(model, attitude, max_workers=max_workers, reuse_directions=reuse)
        _assert_rows_match(rows, baseline)


def _orientations(attitude):
    from cadmetrics.sweep import iter_orientations

    resolved = resolve_sweep_attitude(**attitude)
    return list(iter_orientations(roll=resolved.roll, alpha=resolved.alpha, beta=resolved.beta))


def test_reuse_computes_each_distinct_direction_once(monkeypatch) -> None:
    model = _offset_model(ROOT / "tests/data/unit_cube.stl")
    calls: list[Orientation] = []

    def counting(model, *, orientation=None, direction=None):
        calls.append(orientation)
        return projected_metrics(model, orientation=orientation, direction=direction)

    monkeypatch.setattr(api, "projected_metrics", counting)
    rows = _sweep(model, SWEEP, max_workers=4, reuse_directions=True)

    assert len(rows) == 45
    # 8 alpha steps x 3 non-polar betas, halved by d/-d, plus one shared pole axis.
    assert len(calls) == 13
    computed = {api._direction_key(projection_direction_for_orientation(o)) for o in calls}
    assert len(computed) == len(calls)


def test_direction_key_merges_only_float_noise() -> None:
    direction = projection_direction_for_orientation(Orientation(alpha_deg=30.0, beta_deg=20.0))
    wrapped = projection_direction_for_orientation(Orientation(alpha_deg=390.0, beta_deg=20.0))
    nearby = projection_direction_for_orientation(Orientation(alpha_deg=30.0 + 1e-7, beta_deg=20.0))

    assert api._direction_key(direction) == api._direction_key(-direction)
    assert api._direction_key(direction) == api._direction_key(wrapped)
    assert api._direction_key(direction) != api._direction_key(nearby)
    assert api._direction_key(np.array([0.0, -0.0, 1.0])) == api._direction_key(
        np.array([-0.0, 0.0, -1.0])
    )


def test_parallel_sweep_streams_rows_in_order() -> None:
    model = _offset_model(ROOT / "tests/data/unit_cube.stl")
    progress = []
    rows = sweep_model(
        model,
        **SWEEP,
        progress_callback=lambda index, total, row: progress.append((index, total, row)),
    )

    assert [index for index, _, _ in progress] == list(range(1, len(rows) + 1))
    assert {total for _, total, _ in progress} == {len(rows)}
    assert [row for _, _, row in progress] == rows
    assert all(row.elapsed_sec is not None and row.elapsed_sec >= 0.0 for row in rows)


class _Cancelled(Exception):
    pass


def test_cancel_from_progress_stops_scheduling_new_directions(monkeypatch) -> None:
    model = _offset_model(ROOT / "tests/data/unit_cube.stl")
    calls = 0
    lock = threading.Lock()

    def counting(model, *, orientation=None, direction=None):
        nonlocal calls
        with lock:
            calls += 1
        return projected_metrics(model, orientation=orientation, direction=direction)

    def on_progress(index, total, row):
        if index == 3:
            raise _Cancelled

    monkeypatch.setattr(api, "projected_metrics", counting)
    progress_rows = []
    with pytest.raises(_Cancelled):
        _sweep(
            model,
            {
                "attitude": "alpha-beta",
                "roll_deg": 0.0,
                "alpha_deg": "0:350:10",
                "beta_deg": "-80:80:10",
            },
            max_workers=2,
            reuse_directions=True,
            progress_callback=lambda *args: (progress_rows.append(args), on_progress(*args)),
        )

    assert len(progress_rows) == 3
    # Only a small window of directions is ever queued ahead of the current row.
    assert calls <= 3 + 2 * 2


def test_cancel_while_waiting_returns_without_finishing_running_direction(monkeypatch) -> None:
    model = _offset_model(ROOT / "tests/data/unit_cube.stl")
    started = threading.Event()
    release = threading.Event()
    cancelled = threading.Event()

    def blocking(model, *, orientation=None, direction=None):
        started.set()
        release.wait(timeout=10.0)
        return projected_metrics(model, orientation=orientation, direction=direction)

    def cancel_callback():
        if cancelled.is_set():
            raise _Cancelled

    monkeypatch.setattr(api, "projected_metrics", blocking)
    threading.Timer(0.2, cancelled.set).start()
    begin = time.perf_counter()
    try:
        with pytest.raises(_Cancelled):
            _sweep(
                model,
                SWEEP,
                max_workers=2,
                reuse_directions=True,
                cancel_callback=cancel_callback,
            )
        elapsed = time.perf_counter() - begin
    finally:
        release.set()

    assert started.is_set()
    assert elapsed < 2.0
