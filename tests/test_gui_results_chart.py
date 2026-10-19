from __future__ import annotations

import math
from dataclasses import replace

import pytest

pytest.importorskip("PySide6")

from PySide6 import QtCore

from cadmetrics.gui.results_chart import EMPTY_MESSAGE, MAX_SERIES, chart_data, nice_ticks
from cadmetrics.gui.results_panel import ResultsPanel
from cadmetrics.types import MeasurementRow


def _row(alpha: float, beta: float, area: float) -> MeasurementRow:
    return MeasurementRow(
        file="model.stl",
        input_unit="m",
        output_unit="m",
        roll_deg=0.0,
        alpha_deg=alpha,
        beta_deg=beta,
        volume=1.0,
        surface_area=6.0,
        projected_area=area,
        is_watertight=True,
    )


def _sweep(alphas, betas) -> list[MeasurementRow]:
    return [_row(a, b, 1.0 + a / 90.0 + b / 180.0) for a in alphas for b in betas]


def test_single_angle_sweep_is_one_series() -> None:
    data = chart_data(_sweep((0, 15, 30, 45), (0,)), "alpha_beta")
    assert data.x_label == "Alpha (°)"
    assert data.series_label is None
    assert len(data.series) == 1
    assert [point.x for point in data.series[0].points] == [0, 15, 30, 45]


def test_the_angle_with_more_values_runs_along_x() -> None:
    data = chart_data(_sweep((0, 45), (0, 10, 20, 30)), "alpha_beta")
    assert data.x_label == "Beta (°)"
    assert data.series_label == "Alpha"
    assert [series.value for series in data.series] == [0, 45]
    assert all(len(series.points) == 4 for series in data.series)


def test_too_many_series_or_a_single_attitude_explain_instead_of_plotting() -> None:
    many = chart_data(_sweep(range(MAX_SERIES + 1), range(MAX_SERIES + 1)), "alpha_beta")
    assert many.series == ()
    assert "too many lines" in (many.message or "")
    single = chart_data([_row(0, 0, 1.0)], "alpha_beta")
    assert single.series == () and single.message == EMPTY_MESSAGE
    assert chart_data(_sweep((0, 15), (0,)), "vector").message == EMPTY_MESSAGE


def test_full_sphere_sweep_charts_every_requested_attitude() -> None:
    from pathlib import Path

    from cadmetrics.api import sweep

    sample = (
        Path(__file__).parents[1]
        / "samples"
        / "two_boxes_overlap_projection"
        / "two_boxes_overlap_projection_binary.stl"
    )
    rows = sweep(sample, alpha_deg="0:360:30", beta_deg="-90:90:30")
    data = chart_data(rows, "alpha_beta")

    assert len(rows) == 91
    points = [point for series in data.series for point in series.points]
    assert len(points) == 91
    positions = {(series.value, point.x) for series in data.series for point in series.points}
    assert len(positions) == 91
    assert data.x_label == "Alpha (°)"
    bottom = next(series for series in data.series if series.value == -90)
    assert [point.x for point in bottom.points] == [float(a) for a in range(0, 361, 30)]


def test_nice_ticks_cover_the_range() -> None:
    ticks = nice_ticks(0.78, 3.34)
    assert ticks[0] <= 0.78 and ticks[-1] >= 3.34
    assert len(ticks) <= 8
    assert nice_ticks(2.0, 2.0)[0] < 2.0 < nice_ticks(2.0, 2.0)[-1]


def test_chart_view_follows_rows_and_selection(qtbot) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.resize(900, 320)
    panel.show()
    rows = _sweep((0, 15, 30, 45), (0, 10))
    selected = []
    panel.selected_row_changed.connect(selected.append)
    panel.set_rows(rows)

    panel.chart_view_button.click()
    assert panel.stack.currentWidget() is panel.chart
    assert len(panel.chart.data.series) == 2
    panel.chart.grab()  # Lays out the plot so points map to pixels.

    target = rows.index(replace(rows[0], alpha_deg=30.0, projected_area=1.0 + 30 / 90.0))
    point = next(p for s in panel.chart.data.series for p in s.points if p.row == target)
    qtbot.mouseClick(
        panel.chart, QtCore.Qt.MouseButton.LeftButton, pos=panel.chart._map(point).toPoint()
    )
    assert selected[-1] is rows[target]
    assert panel.chart._selected == target

    panel.mark_stale()
    assert panel.chart._stale is True
    assert panel.chart._selected is None

    panel.table_view_button.click()
    assert panel.stack.currentWidget() is panel.table


@pytest.mark.parametrize("scale", (1e-18, 1e-6, 1.0, 1e6, 1e18))
def test_nice_ticks_cover_nearly_constant_ranges(scale: float) -> None:
    high = math.nextafter(scale, math.inf)
    ticks = nice_ticks(scale, high)
    assert 2 <= len(ticks) <= 8
    assert ticks[0] <= scale < high <= ticks[-1]
    assert all(math.isfinite(tick) for tick in ticks)
    assert all(left < right for left, right in zip(ticks, ticks[1:]))


@pytest.mark.parametrize("low, high", ((1e-15, 3e-15), (0.0, 1e-15)))
def test_nice_ticks_preserve_small_positive_areas(low: float, high: float) -> None:
    ticks = nice_ticks(low, high)
    assert 2 <= len(ticks) <= 8
    assert ticks[0] <= low < high <= ticks[-1]
    assert all(left < right for left, right in zip(ticks, ticks[1:]))
    assert 0.0 < ticks[-1] < high * 2
