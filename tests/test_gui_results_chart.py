from __future__ import annotations

import math
from dataclasses import replace

import pytest

pytest.importorskip("PySide6")

from PySide6 import QtCore, QtGui, QtWidgets

from cadmetrics.gui.results_chart import (
    EMPTY_MESSAGE,
    MAX_SERIES,
    SERIES_COLORS,
    chart_data,
    nice_ticks,
    series_colors,
)
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


def test_more_lines_than_hues_shade_one_ramp_light_to_dark(qtbot) -> None:
    data = chart_data(_sweep(range(0, 91, 5), range(0, 15 * 5, 5)), "alpha_beta")
    assert len(data.series) == 15
    colors = series_colors(15)
    assert len(set(colors)) == 15
    assert series_colors(len(SERIES_COLORS)) == list(SERIES_COLORS)
    lightness = [QtGui.QColor(color).lightnessF() for color in colors]
    assert lightness == sorted(lightness, reverse=True)

    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.resize(900, 320)
    panel.show()
    panel.set_rows(_sweep(range(0, 91, 5), range(0, 15 * 5, 5)))
    panel.chart_view_button.click()
    assert len(panel.chart.data.series) == 15
    panel.chart.grab()


def test_the_x_axis_can_be_chosen() -> None:
    rows = _sweep((0, 45), (0, 10, 20, 30))
    data = chart_data(rows, "alpha_beta", "alpha_deg")
    assert data.x_label == "Alpha (°)"
    assert data.series_label == "Beta"
    assert [series.value for series in data.series] == [0, 10, 20, 30]
    assert chart_data(rows, "alpha_beta", "beta_deg").x_label == "Beta (°)"
    single = chart_data(_sweep((0,), (0, 10, 20)), "alpha_beta", "alpha_deg")
    assert single.series == ()
    assert "Alpha has a single value" in (single.message or "")


def test_x_axis_combo_follows_mode_and_view(qtbot) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.set_rows(_sweep((0, 45), (0, 10, 20, 30)))
    assert not panel.x_axis_combo.isVisible()
    panel.chart_view_button.click()
    assert panel.x_axis_combo.isVisible()
    assert [panel.x_axis_combo.itemText(i) for i in range(3)] == ["Auto", "Alpha", "Beta"]
    assert panel.chart.data.x_label == "Beta (°)"
    panel.x_axis_combo.setCurrentIndex(1)
    assert panel.chart.data.x_label == "Alpha (°)"
    panel.set_attitude_mode("roll_pitch")
    assert panel.x_axis_combo.currentData() is None
    assert panel.x_axis_combo.itemText(1) == "Roll"


def test_chart_saves_as_png_or_svg(qtbot, tmp_path) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.resize(800, 360)
    panel.show()
    panel.set_rows(_sweep((0, 15, 30, 45), (0, 10)))
    assert not panel.save_image_button.isVisible()
    panel.chart_view_button.click()
    assert panel.save_image_button.isVisible() and panel.save_image_button.isEnabled()

    png = tmp_path / "chart.png"
    panel.save_image(png)
    image = QtGui.QImage(str(png))
    assert image.width() == panel.chart.width() * 2
    svg = tmp_path / "chart.svg"
    panel.save_image(svg)
    assert "<svg" in svg.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="PNG or SVG"):
        panel.save_image(tmp_path / "chart.jpg")

    panel.set_rows([_row(0, 0, 1.0)])  # A single attitude has no chart to save.
    assert not panel.save_image_button.isEnabled()
    with pytest.raises(ValueError, match="no chart"):
        panel.save_image(tmp_path / "empty.png")


_FILTERS = {".png": "PNG Image (*.png)", ".svg": "SVG Image (*.svg)"}


@pytest.fixture
def chart_panel(qtbot):
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.resize(800, 360)
    panel.show()
    panel.set_rows(_sweep((0, 15, 30, 45), (0, 10)))
    panel.chart_view_button.click()
    return panel


def _choose(monkeypatch, panel, returned, selected_filter, answer=None):
    """Run choose_image_path with a mocked dialog; return (saved paths, questions asked)."""
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (returned, selected_filter)),
    )
    questions = []

    def question(*args):
        questions.append(args)
        return answer

    monkeypatch.setattr(QtWidgets.QMessageBox, "question", staticmethod(question))
    saved = []
    original = panel.save_image
    monkeypatch.setattr(panel, "save_image", lambda path: (saved.append(path), original(path)))
    panel.choose_image_path()
    return saved, questions


@pytest.mark.parametrize("suffix", (".png", ".svg"))
@pytest.mark.parametrize(
    "answer",
    (QtWidgets.QMessageBox.StandardButton.No, QtWidgets.QMessageBox.StandardButton.Cancel),
)
def test_declining_to_replace_a_completed_name_keeps_the_file(
    chart_panel, monkeypatch, tmp_path, suffix, answer
) -> None:
    existing = tmp_path / f"report{suffix}"
    existing.write_bytes(b"keep me")
    saved, questions = _choose(
        monkeypatch, chart_panel, str(tmp_path / "report"), _FILTERS[suffix], answer
    )
    assert len(questions) == 1
    # Not replacing is the default button.
    assert questions[0][-1] == QtWidgets.QMessageBox.StandardButton.No
    assert saved == []
    assert existing.read_bytes() == b"keep me"


@pytest.mark.parametrize("suffix", (".png", ".svg"))
def test_replacing_a_completed_name_saves_there(chart_panel, monkeypatch, tmp_path, suffix) -> None:
    existing = tmp_path / f"report{suffix}"
    existing.write_bytes(b"old")
    saved, questions = _choose(
        monkeypatch,
        chart_panel,
        str(tmp_path / "report"),
        _FILTERS[suffix],
        QtWidgets.QMessageBox.StandardButton.Yes,
    )
    assert len(questions) == 1
    assert saved == [str(existing)]
    assert existing.read_bytes() != b"old"


@pytest.mark.parametrize("suffix", (".png", ".svg"))
def test_a_new_completed_name_saves_without_asking(
    chart_panel, monkeypatch, tmp_path, suffix
) -> None:
    saved, questions = _choose(monkeypatch, chart_panel, str(tmp_path / "report"), _FILTERS[suffix])
    assert questions == []
    assert saved == [str(tmp_path / f"report{suffix}")]
    assert (tmp_path / f"report{suffix}").stat().st_size > 0


@pytest.mark.parametrize("suffix", (".png", ".svg"))
def test_a_name_with_its_suffix_relies_on_the_dialogs_confirmation(
    chart_panel, monkeypatch, tmp_path, suffix
) -> None:
    existing = tmp_path / f"report{suffix}"
    existing.write_bytes(b"old")  # The dialog already asked about this exact file.
    saved, questions = _choose(monkeypatch, chart_panel, str(existing), _FILTERS[suffix])
    assert questions == []
    assert saved == [str(existing)]
    assert existing.read_bytes() != b"old"


@pytest.mark.parametrize("suffix", (".png", ".svg"))
def test_cancelling_the_save_dialog_saves_nothing(
    chart_panel, monkeypatch, tmp_path, suffix
) -> None:
    saved, questions = _choose(monkeypatch, chart_panel, "", _FILTERS[suffix])
    assert saved == [] and questions == []
    assert list(tmp_path.iterdir()) == []
