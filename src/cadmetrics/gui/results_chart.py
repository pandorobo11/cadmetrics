"""Line chart of projected area across an attitude sweep."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

from cadmetrics.types import MeasurementRow

# Reference categorical palette, fixed order (validated on the white chart surface).
SERIES_COLORS = (
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#6250d6",
    "#e34948",
)
MAX_SERIES = len(SERIES_COLORS)
_SURFACE = "#ffffff"
_TEXT = "#202832"
_MUTED_TEXT = "#5f6b78"
_GRID = "#e1e5ea"
_AXIS = "#b8c1cb"
_LINE_WIDTH = 2.0
_MARKER = 8.0
_SELECTED_MARKER = 12.0
_HIT_RADIUS = 14.0
_STALE_OPACITY = 0.45
# (x field, series field, x label, series label) per attitude mode.
_AXES = {
    "alpha_beta": (("alpha_deg", "Alpha"), ("beta_deg", "Beta")),
    "roll_pitch": (("roll_deg", "Roll"), ("pitch_deg", "Pitch")),
}
EMPTY_MESSAGE = "The chart needs an Alpha / Beta or Roll / Pitch sweep with several attitudes."


@dataclass(frozen=True)
class ChartPoint:
    x: float
    y: float
    row: int  # Index into the rows given to the chart.


@dataclass(frozen=True)
class ChartSeries:
    value: float | None  # The series variable's value, or None for a single series.
    points: tuple[ChartPoint, ...]


@dataclass(frozen=True)
class ChartData:
    x_label: str
    series_label: str | None
    series: tuple[ChartSeries, ...]
    message: str | None = None


def _key(value: float | None) -> float:
    # Group values that differ only by floating-point noise from the sweep generator.
    return round(float(value or 0.0) + 0.0, 9)


def chart_data(rows: Sequence[MeasurementRow], mode: str) -> ChartData:
    """Split sweep rows into one series per value of the less-varied angle."""
    if mode not in _AXES:
        return ChartData("", None, (), EMPTY_MESSAGE)
    first, second = _AXES[mode]
    usable = [
        (index, row, row.projected_area)
        for index, row in enumerate(rows)
        if row.projected_area is not None
    ]
    first_values = {_key(getattr(row, first[0])) for _, row, _ in usable}
    second_values = {_key(getattr(row, second[0])) for _, row, _ in usable}
    # The angle with more values runs along the x axis; ties keep the first angle there.
    (x_field, x_name), (s_field, s_name) = (
        (second, first) if len(second_values) > len(first_values) else (first, second)
    )
    groups: dict[float, list[ChartPoint]] = {}
    for index, row, area in usable:
        point = ChartPoint(_key(getattr(row, x_field)), float(area), index)
        groups.setdefault(_key(getattr(row, s_field)), []).append(point)
    x_label = f"{x_name} (°)"
    if not groups or max(len(points) for points in groups.values()) < 2:
        return ChartData(x_label, None, (), EMPTY_MESSAGE)
    if len(groups) > MAX_SERIES:
        return ChartData(
            x_label,
            None,
            (),
            f"{len(groups)} {s_name} values are too many lines to compare; "
            f"the chart shows up to {MAX_SERIES}. Use the table, or sweep fewer {s_name} values.",
        )
    series = tuple(
        ChartSeries(
            value if len(groups) > 1 else None,
            tuple(sorted(points, key=lambda point: point.x)),
        )
        for value, points in sorted(groups.items())
    )
    return ChartData(x_label, s_name if len(groups) > 1 else None, series)


def nice_ticks(low: float, high: float, target: int = 5) -> list[float]:
    """Round tick values covering [low, high]."""
    if not math.isfinite(low) or not math.isfinite(high):
        return [0.0]
    if high <= low:
        spread = abs(low) * 0.1 or 1.0
        low, high = low - spread, high + spread
    raw = (high - low) / max(target - 1, 1)
    magnitude = 10.0 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    start = math.floor(low / step) * step
    ticks = []
    value = start
    while value < high + step * 0.5:
        ticks.append(round(value, 12) + 0.0)
        value += step
    if ticks[-1] < high:
        ticks.append(round(ticks[-1] + step, 12))
    return ticks


def _format_tick(value: float) -> str:
    return f"{value:.6g}"


class ResultsChart(QtWidgets.QWidget):
    """Projected area against the swept angle; click a point to select its row."""

    row_clicked = QtCore.Signal(int)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("resultsChart")
        self.setMouseTracking(True)
        self.setMinimumHeight(160)
        self._rows: list[MeasurementRow] = []
        self._mode = "alpha_beta"
        self._data = ChartData("", None, (), EMPTY_MESSAGE)
        self._selected: int | None = None
        self._hovered: int | None = None
        self._stale = False
        self._plot = QtCore.QRectF()
        self._x_range = (0.0, 1.0)
        self._y_range = (0.0, 1.0)

    @property
    def data(self) -> ChartData:
        return self._data

    def set_rows(self, rows: Sequence[MeasurementRow], mode: str) -> None:
        self._rows = list(rows)
        self._mode = mode
        self._data = chart_data(self._rows, mode)
        if self._selected is not None and self._selected >= len(self._rows):
            self._selected = None
        self._hovered = None
        self.update()

    def set_selected(self, row: int | None) -> None:
        if row != self._selected:
            self._selected = row
            self.update()

    def set_stale(self, stale: bool) -> None:
        if stale != self._stale:
            self._stale = stale
            self.update()

    def point_at(self, position: QtCore.QPointF) -> ChartPoint | None:
        """Nearest point within the hit radius, which is larger than the marker."""
        best: ChartPoint | None = None
        best_distance = _HIT_RADIUS
        for series in self._data.series:
            for point in series.points:
                distance = QtCore.QLineF(position, self._map(point)).length()
                if distance <= best_distance:
                    best, best_distance = point, distance
        return best

    def _y_unit(self) -> str:
        unit = self._rows[0].output_unit if self._rows else ""
        return f" ({unit}²)" if unit else ""

    # Layout -------------------------------------------------------------------------

    def _layout(self) -> tuple[list[float], list[float]]:
        points = [point for series in self._data.series for point in series.points]
        xs = [point.x for point in points]
        ys = [point.y for point in points]
        x_ticks = nice_ticks(min(xs), max(xs), target=7)
        # Areas are magnitudes; start at zero unless the data sits far above it.
        y_low = 0.0 if min(ys) <= 0.5 * max(ys) else min(ys)
        y_ticks = nice_ticks(y_low, max(ys), target=5)
        self._x_range = (min(xs), max(xs)) if max(xs) > min(xs) else (x_ticks[0], x_ticks[-1])
        self._y_range = (y_ticks[0], y_ticks[-1])
        metrics = self.fontMetrics()
        left = max(metrics.horizontalAdvance(_format_tick(tick)) for tick in y_ticks) + 22
        legend = metrics.height() + 14 if self._data.series_label else 8
        top = legend + metrics.height() + 6  # Room for the y-axis title above the plot.
        bottom = metrics.height() * 2 + 16
        right = 18 + self._direct_label_width()
        self._plot = QtCore.QRectF(
            left, top, max(self.width() - left - right, 10), max(self.height() - top - bottom, 10)
        )
        return x_ticks, y_ticks

    def _map(self, point: ChartPoint) -> QtCore.QPointF:
        return self._map_xy(point.x, point.y)

    def _map_xy(self, x: float, y: float) -> QtCore.QPointF:
        (x0, x1), (y0, y1) = self._x_range, self._y_range
        plot = self._plot
        fx = 0.5 if x1 == x0 else (x - x0) / (x1 - x0)
        fy = 0.5 if y1 == y0 else (y - y0) / (y1 - y0)
        return QtCore.QPointF(plot.left() + fx * plot.width(), plot.bottom() - fy * plot.height())

    def _series_name(self, series: ChartSeries) -> str:
        return f"{self._data.series_label} {series.value:g}°"

    def _direct_labels(self) -> bool:
        return 2 <= len(self._data.series) <= 4

    def _direct_label_width(self) -> int:
        if not self._direct_labels():
            return 0
        metrics = self.fontMetrics()
        return max(metrics.horizontalAdvance(f"{s.value:g}°") for s in self._data.series) + 10

    # Painting -----------------------------------------------------------------------

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(_SURFACE))
        if not self._data.series:
            painter.setPen(QtGui.QColor(_MUTED_TEXT))
            painter.drawText(
                self.rect().adjusted(24, 12, -24, -12),
                QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.TextFlag.TextWordWrap,
                self._data.message or EMPTY_MESSAGE,
            )
            return
        x_ticks, y_ticks = self._layout()
        self._paint_axes(painter, x_ticks, y_ticks)
        if self._stale:
            painter.setOpacity(_STALE_OPACITY)
        self._paint_series(painter)
        painter.setOpacity(1.0)
        self._paint_legend(painter)

    def _paint_axes(
        self, painter: QtGui.QPainter, x_ticks: list[float], y_ticks: list[float]
    ) -> None:
        plot = self._plot
        metrics = self.fontMetrics()
        grid = QtGui.QPen(QtGui.QColor(_GRID), 1.0)
        painter.setFont(self.font())
        for tick in y_ticks:
            y = self._map_xy(self._x_range[0], tick).y()
            painter.setPen(grid)
            painter.drawLine(QtCore.QPointF(plot.left(), y), QtCore.QPointF(plot.right(), y))
            painter.setPen(QtGui.QColor(_MUTED_TEXT))
            text = _format_tick(tick)
            painter.drawText(
                QtCore.QPointF(
                    plot.left() - 8 - metrics.horizontalAdvance(text), y + metrics.ascent() / 2 - 1
                ),
                text,
            )
        x0, x1 = self._x_range
        for tick in x_ticks:
            if tick < x0 - 1e-9 or tick > x1 + 1e-9:
                continue
            x = self._map_xy(tick, self._y_range[0]).x()
            painter.setPen(QtGui.QColor(_MUTED_TEXT))
            text = f"{tick:g}"
            painter.drawText(
                QtCore.QPointF(
                    x - metrics.horizontalAdvance(text) / 2, plot.bottom() + metrics.height() + 4
                ),
                text,
            )
        painter.setPen(QtGui.QPen(QtGui.QColor(_AXIS), 1.0))
        painter.drawLine(plot.bottomLeft(), plot.bottomRight())
        painter.setPen(QtGui.QColor(_MUTED_TEXT))
        x_title = self._data.x_label
        painter.drawText(
            QtCore.QPointF(
                plot.center().x() - metrics.horizontalAdvance(x_title) / 2,
                plot.bottom() + metrics.height() * 2 + 10,
            ),
            x_title,
        )
        painter.drawText(QtCore.QPointF(8, plot.top() - 8), f"Projected area{self._y_unit()}")

    def _paint_series(self, painter: QtGui.QPainter) -> None:
        surface = QtGui.QColor(_SURFACE)
        for index, series in enumerate(self._data.series):
            color = QtGui.QColor(SERIES_COLORS[index])
            pen = QtGui.QPen(color, _LINE_WIDTH)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPolyline(QtGui.QPolygonF([self._map(point) for point in series.points]))
            # Markers wear a surface ring so they stay legible where lines cross.
            painter.setPen(QtGui.QPen(surface, 2.0))
            painter.setBrush(color)
            for point in series.points:
                painter.drawEllipse(self._map(point), _MARKER / 2, _MARKER / 2)
        if self._direct_labels():
            self._paint_direct_labels(painter)
        self._paint_focus(painter)

    def _paint_direct_labels(self, painter: QtGui.QPainter) -> None:
        metrics = self.fontMetrics()
        ends = sorted(
            (self._map(series.points[-1]).y(), index)
            for index, series in enumerate(self._data.series)
        )
        # Labels that would collide are left to the legend instead of being nudged.
        if any(b[0] - a[0] < metrics.height() for a, b in zip(ends, ends[1:])):
            return
        painter.setPen(QtGui.QColor(_TEXT))
        for y, index in ends:
            series = self._data.series[index]
            painter.drawText(
                QtCore.QPointF(self._plot.right() + 10, y + metrics.ascent() / 2 - 1),
                f"{series.value:g}°",
            )

    def _point_for_row(self, row: int | None) -> tuple[int, ChartPoint] | None:
        if row is None:
            return None
        for index, series in enumerate(self._data.series):
            for point in series.points:
                if point.row == row:
                    return index, point
        return None

    def _paint_focus(self, painter: QtGui.QPainter) -> None:
        for row, size in ((self._hovered, _MARKER + 2), (self._selected, _SELECTED_MARKER)):
            found = self._point_for_row(row)
            if found is None:
                continue
            index, point = found
            center = self._map(point)
            painter.setOpacity(1.0)
            if row == self._selected:
                painter.setPen(QtGui.QPen(QtGui.QColor(_AXIS), 1.0))
                painter.drawLine(
                    QtCore.QPointF(center.x(), self._plot.top()),
                    QtCore.QPointF(center.x(), self._plot.bottom()),
                )
            painter.setPen(QtGui.QPen(QtGui.QColor(_TEXT), 2.0))
            painter.setBrush(QtGui.QColor(SERIES_COLORS[index]))
            painter.drawEllipse(center, size / 2, size / 2)

    def _paint_legend(self, painter: QtGui.QPainter) -> None:
        if not self._data.series_label:
            return
        metrics = self.fontMetrics()
        x = self._plot.left()
        y = 6 + metrics.height() / 2
        for index, series in enumerate(self._data.series):
            painter.setPen(QtGui.QPen(QtGui.QColor(SERIES_COLORS[index]), 3.0))
            painter.drawLine(QtCore.QPointF(x, y), QtCore.QPointF(x + 16, y))
            painter.setPen(QtGui.QColor(_TEXT))
            name = self._series_name(series)
            painter.drawText(QtCore.QPointF(x + 22, y + metrics.ascent() / 2 - 1), name)
            x += 22 + metrics.horizontalAdvance(name) + 16

    # Interaction --------------------------------------------------------------------

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        point = self.point_at(event.position())
        hovered = None if point is None else point.row
        if hovered != self._hovered:
            self._hovered = hovered
            self.update()
        if point is None:
            QtWidgets.QToolTip.hideText()
            self.unsetCursor()
            return
        row = self._rows[point.row]
        unit = row.output_unit
        lines = []
        if self._data.series_label:
            series = next(s for s in self._data.series if point in s.points)
            lines.append(self._series_name(series))
        lines.append(f"{self._data.x_label.removesuffix(' (°)')} {point.x:g}°")
        lines.append(f"Projected area {point.y:.6g} {unit}²")
        QtWidgets.QToolTip.showText(
            event.globalPosition().toPoint(), "\n".join(lines), self, QtCore.QRect(), 4000
        )
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

    def leaveEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802
        self._hovered = None
        self.unsetCursor()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        point = self.point_at(event.position())
        if point is not None and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.row_clicked.emit(point.row)
            return
        super().mousePressEvent(event)
