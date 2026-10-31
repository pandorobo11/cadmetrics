"""Line chart of projected area across an attitude sweep."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

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
# Beyond the categorical palette, lines are ordered angles: shade them along one hue,
# light to dark (ordinal steps 250-700, each at least 2:1 against the surface).
ORDINAL_RAMP = (
    "#86b6ef",
    "#6da7ec",
    "#5598e7",
    "#3987e5",
    "#2a78d6",
    "#256abf",
    "#1c5cab",
    "#184f95",
    "#104281",
    "#0d366b",
)
MAX_SERIES = 24
# Dashed reference curves, and thin detail lines under a series (at least 2:1 on the surface).
REFERENCE_COLOR = "#5f6b78"
DETAIL_COLOR = "#9aa5b1"
_SURFACE = "#ffffff"
_TEXT = "#202832"
_MUTED_TEXT = REFERENCE_COLOR
_GRID = "#e1e5ea"
_AXIS = "#b8c1cb"
_LINE_WIDTH = 2.0
_MARKER = 8.0
_SELECTED_MARKER = 12.0
_HIT_RADIUS = 14.0
_STALE_OPACITY = 0.45
_DIMMED_OPACITY = 0.18
# ((first field, label), (second field, label)) per attitude mode.
AXES = {
    "alpha_beta": (("alpha_deg", "Alpha"), ("beta_deg", "Beta")),
    "roll_pitch": (("roll_deg", "Roll"), ("pitch_deg", "Pitch")),
}
IMAGE_SUFFIXES = (".png", ".svg")
_PNG_SCALE = 2  # Pixels per point, so saved charts stay sharp on high-density displays.
EMPTY_MESSAGE = "The chart needs an Alpha / Beta or Roll / Pitch sweep with several attitudes."


@dataclass(frozen=True)
class ChartPoint:
    x: float
    y: float
    row: int  # Index into the rows given to the chart; negative for a point that is no row.


@dataclass(frozen=True)
class ChartSeries:
    value: float | None  # The series variable's value, or None for a single series.
    points: tuple[ChartPoint, ...]


@dataclass(frozen=True)
class ChartLine:
    """A line drawn under the series, such as a reference curve; it is not clickable."""

    points: tuple[tuple[float, float], ...]
    color: str
    label: str | None = None
    dashed: bool = False
    width: float = 1.5
    # False leaves the line out of the y range; it is clipped to the plot instead.
    scales_axis: bool = True


@dataclass(frozen=True)
class LegendEntry:
    color: str
    name: str
    dashed: bool = False


@dataclass(frozen=True)
class ChartData:
    x_label: str
    series_label: str | None
    series: tuple[ChartSeries, ...]
    message: str | None = None


def _key(value: float | None) -> float:
    # Group values that differ only by floating-point noise from the sweep generator.
    return round(float(value or 0.0) + 0.0, 9)


def series_colors(count: int) -> list[str]:
    """Categorical hues in fixed order, or an ordinal ramp for more lines than hues."""
    if count <= len(SERIES_COLORS):
        return list(SERIES_COLORS[:count])
    last = len(ORDINAL_RAMP) - 1
    colors = []
    for index in range(count):
        position = index * last / (count - 1)
        low = min(int(position), last - 1)
        a = QtGui.QColor(ORDINAL_RAMP[low])
        b = QtGui.QColor(ORDINAL_RAMP[low + 1])
        t = position - low
        mixed = QtGui.QColor(
            round(a.red() + (b.red() - a.red()) * t),
            round(a.green() + (b.green() - a.green()) * t),
            round(a.blue() + (b.blue() - a.blue()) * t),
        )
        colors.append(mixed.name())
    return colors


def chart_data(rows: Sequence[MeasurementRow], mode: str, x_field: str | None = None) -> ChartData:
    """Split sweep rows into one series per value of the angle not on the x axis.

    ``x_field`` picks the x-axis angle; ``None`` puts the angle with more values there.
    """
    if mode not in AXES:
        return ChartData("", None, (), EMPTY_MESSAGE)
    first, second = AXES[mode]
    usable = [
        (index, row, row.projected_area)
        for index, row in enumerate(rows)
        if row.projected_area is not None
    ]
    first_values = {_key(getattr(row, first[0])) for _, row, _ in usable}
    second_values = {_key(getattr(row, second[0])) for _, row, _ in usable}
    if x_field == second[0]:
        swap = True
    elif x_field == first[0]:
        swap = False
    else:
        # The angle with more values runs along the x axis; ties keep the first angle there.
        swap = len(second_values) > len(first_values)
    x_values = second_values if swap else first_values
    (x_field, x_name), (s_field, s_name) = (second, first) if swap else (first, second)
    groups: dict[float, list[ChartPoint]] = {}
    for index, row, area in usable:
        point = ChartPoint(_key(getattr(row, x_field)), float(area), index)
        groups.setdefault(_key(getattr(row, s_field)), []).append(point)
    x_label = f"{x_name} (°)"
    if not groups or max(len(points) for points in groups.values()) < 2:
        if usable and len(x_values) == 1 and len(groups) > 1:
            return ChartData(
                x_label,
                None,
                (),
                f"{x_name} has a single value in this sweep; plot {s_name} along the x axis.",
            )
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
    # Treat roundoff-sized variation like a constant range, not a microscopic axis.
    if high <= low or math.isclose(low, high, rel_tol=1e-12, abs_tol=0.0):
        spread = abs(low) * 0.1 or 1.0
        low, high = low - spread, high + spread
    raw = (high - low) / max(target - 1, 1)
    magnitude = 10.0 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    start = math.floor(low / step)
    stop = math.ceil(high / step)
    # Integer indices guarantee progress. Keep the scale instead of rounding small
    # areas to zero at a fixed number of decimal places.
    return [index * step + 0.0 for index in range(start, stop + 1)]


def _format_tick(value: float) -> str:
    return f"{value:.6g}"


class ResultsChart(QtWidgets.QWidget):
    """Projected area against the swept angle; click a point to select its row."""

    row_clicked = QtCore.Signal(int)
    # Subclasses plotting other values override these and the hooks below.
    y_title = "Projected area"
    show_markers = True

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("resultsChart")
        self.setMouseTracking(True)
        self.setMinimumHeight(160)
        self._rows: list[MeasurementRow] = []
        self._mode = "alpha_beta"
        self._x_field: str | None = None
        self._data = ChartData("", None, (), EMPTY_MESSAGE)
        self._colors: list[str] = []
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
        self._refresh()

    def set_x_field(self, x_field: str | None) -> None:
        """Plot this angle along x; ``None`` picks the angle with more values."""
        if x_field != self._x_field:
            self._x_field = x_field
            self._refresh()

    def _refresh(self) -> None:
        self._data = chart_data(self._rows, self._mode, self._x_field)
        self._colors = series_colors(len(self._data.series))
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

    def save_image(self, path: str | Path) -> None:
        """Save the chart as it is shown, as PNG or SVG by the file's suffix."""
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            raise ValueError(
                f"Chart images are saved as PNG or SVG, not {path.suffix or path.name}."
            )
        if not self._data.series:
            raise ValueError("There is no chart to save.")
        # The pointer's highlight is transient; the saved chart keeps only the selection.
        hovered, self._hovered = self._hovered, None
        try:
            if suffix == ".svg":
                generator = QtSvg.QSvgGenerator()
                generator.setFileName(str(path))
                generator.setSize(self.size())
                generator.setViewBox(self.rect())
                generator.setTitle(self.y_title)
                self.render(generator)
                # QSvgGenerator reports no write errors; an empty file means it failed.
                if not path.is_file() or path.stat().st_size == 0:
                    raise OSError(f"Could not write {path}.")
            else:
                image = QtGui.QImage(self.size() * _PNG_SCALE, QtGui.QImage.Format.Format_ARGB32)
                image.setDevicePixelRatio(_PNG_SCALE)
                image.fill(QtGui.QColor(_SURFACE))
                self.render(image)
                if not image.save(str(path)):  # The checked suffix picks PNG.
                    raise OSError(f"Could not write {path}.")
        finally:
            self._hovered = hovered

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

    def _overlay_lines(self) -> list[ChartLine]:
        """Lines drawn under the series, such as reference curves; none by default."""
        return []

    def _extra_y_values(self) -> list[float]:
        """Values drawn outside the series and lines that the y range must include."""
        return []

    def _x_extent(self, xs: list[float]) -> tuple[float, float]:
        return min(xs), max(xs)

    def _x_ticks(self, low: float, high: float) -> list[float]:
        return nice_ticks(low, high, target=7)

    def _layout(self) -> tuple[list[float], list[float]]:
        points = [point for series in self._data.series for point in series.points]
        x_low, x_high = self._x_extent([point.x for point in points])
        ys = [point.y for point in points] + [
            y for line in self._overlay_lines() if line.scales_axis for _, y in line.points
        ]
        ys += self._extra_y_values()
        x_ticks = self._x_ticks(x_low, x_high)
        # Areas are magnitudes; start at zero unless the data sits far above it. Values
        # that change sign, such as slopes, keep both sides of zero.
        low, high = min(ys), max(ys)
        y_low = low if low < 0.0 or low > 0.5 * high else 0.0
        y_ticks = nice_ticks(y_low, max(high, 0.0), target=5)
        self._x_range = (x_low, x_high) if x_high > x_low else (x_ticks[0], x_ticks[-1])
        self._y_range = (y_ticks[0], y_ticks[-1])
        metrics = self.fontMetrics()
        left = max(metrics.horizontalAdvance(_format_tick(tick)) for tick in y_ticks) + 22
        legend = self._legend_height() if self._legend_entries() else 8
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
        if self._y_range[0] < 0.0 < self._y_range[1]:
            zero = self._map_xy(x0, 0.0).y()
            painter.drawLine(QtCore.QPointF(plot.left(), zero), QtCore.QPointF(plot.right(), zero))
        painter.setPen(QtGui.QColor(_MUTED_TEXT))
        x_title = self._data.x_label
        painter.drawText(
            QtCore.QPointF(
                plot.center().x() - metrics.horizontalAdvance(x_title) / 2,
                plot.bottom() + metrics.height() * 2 + 10,
            ),
            x_title,
        )
        painter.drawText(QtCore.QPointF(8, plot.top() - 8), f"{self.y_title}{self._y_unit()}")

    def _hovered_series(self) -> int | None:
        found = self._point_for_row(self._hovered)
        return None if found is None or len(self._data.series) < 2 else found[0]

    def _paint_series(self, painter: QtGui.QPainter) -> None:
        surface = QtGui.QColor(_SURFACE)
        base_opacity = painter.opacity()
        painter.save()
        painter.setClipRect(self._plot.adjusted(-2, -2, 2, 2))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        for line in self._overlay_lines():
            if len(line.points) < 2:
                continue
            style = QtCore.Qt.PenStyle.DashLine if line.dashed else QtCore.Qt.PenStyle.SolidLine
            painter.setPen(QtGui.QPen(QtGui.QColor(line.color), line.width, style))
            painter.drawPolyline(QtGui.QPolygonF([self._map_xy(x, y) for x, y in line.points]))
        painter.restore()
        hovered = self._hovered_series()
        order = list(range(len(self._data.series)))
        if hovered is not None:
            # Pointing at a line lifts it above the others, which step back.
            order.remove(hovered)
            order.append(hovered)
        for index in order:
            series = self._data.series[index]
            dimmed = hovered is not None and index != hovered
            painter.setOpacity(base_opacity * (_DIMMED_OPACITY if dimmed else 1.0))
            color = QtGui.QColor(self._colors[index])
            pen = QtGui.QPen(color, _LINE_WIDTH)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPolyline(QtGui.QPolygonF([self._map(point) for point in series.points]))
            if not self.show_markers:
                continue
            # Markers wear a surface ring so they stay legible where lines cross.
            painter.setPen(QtGui.QPen(surface, 2.0))
            painter.setBrush(color)
            for point in series.points:
                painter.drawEllipse(self._map(point), _MARKER / 2, _MARKER / 2)
        painter.setOpacity(base_opacity)
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
            painter.setBrush(QtGui.QColor(self._colors[index]))
            painter.drawEllipse(center, size / 2, size / 2)

    def _legend_entries(self) -> list[LegendEntry]:
        """One entry per series when there are several; none for a single line."""
        if not self._data.series_label:
            return []
        return [
            LegendEntry(self._colors[index], self._series_name(series))
            for index, series in enumerate(self._data.series)
        ]

    def _legend_rows(self) -> list[list[tuple[LegendEntry, float]]]:
        """Categorical legend entries wrapped to the plot width, with their widths."""
        metrics = self.fontMetrics()
        available = max(self.width() - 60.0, 120.0)
        rows: list[list[tuple[LegendEntry, float]]] = [[]]
        used = 0.0
        for entry in self._legend_entries():
            width = 22 + metrics.horizontalAdvance(entry.name) + 16
            if rows[-1] and used + width > available:
                rows.append([])
                used = 0.0
            rows[-1].append((entry, width))
            used += width
        return rows

    def _ordinal_legend(self) -> bool:
        return len(self._data.series) > len(SERIES_COLORS)

    def _legend_height(self) -> float:
        line = self.fontMetrics().height() + 4
        rows = 1 if self._ordinal_legend() else len(self._legend_rows())
        return rows * line + 10

    def _paint_legend(self, painter: QtGui.QPainter) -> None:
        if not self._legend_entries():
            return
        metrics = self.fontMetrics()
        line = metrics.height() + 4
        if self._ordinal_legend():
            self._paint_ordinal_legend(painter)
            return
        for row_index, row in enumerate(self._legend_rows()):
            x = self._plot.left()
            y = 6 + metrics.height() / 2 + row_index * line
            for entry, width in row:
                pen = QtGui.QPen(QtGui.QColor(entry.color), 1.5 if entry.dashed else 3.0)
                if entry.dashed:
                    pen.setStyle(QtCore.Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(QtCore.QPointF(x, y), QtCore.QPointF(x + 16, y))
                painter.setPen(QtGui.QColor(_TEXT))
                painter.drawText(QtCore.QPointF(x + 22, y + metrics.ascent() / 2 - 1), entry.name)
                x += width

    def _ordinal_legend_items(self) -> tuple[list[tuple[QtCore.QPointF, str]], list[QtCore.QRectF]]:
        """Texts and swatches of the ordinal key, narrowed to fit the chart's width.

        Swatches shrink first, then the key moves left of the plot, then the line count goes,
        so the first and last values stay readable.
        """
        metrics = self.fontMetrics()
        series = self._data.series
        first, last = f"{series[0].value:g}°", f"{series[-1].value:g}°"
        right = self.width() - 8.0
        min_step = 3.0
        for label, left in (
            (f"{self._data.series_label} ({len(series)} lines)", self._plot.left()),
            (f"{self._data.series_label} ({len(series)} lines)", 8.0),
            (self._data.series_label or "", 8.0),
        ):
            texts = metrics.horizontalAdvance(label) + 8 + metrics.horizontalAdvance(first) + 8
            room = right - left - texts - 6 - metrics.horizontalAdvance(last)
            if room >= min_step * len(series):
                break
        step = min(max(room / len(series), min_step), 12.0)
        swatch = step - 2 if step >= 6 else step
        y = 6 + metrics.height() / 2
        baseline = y + metrics.ascent() / 2 - 1
        x = left
        items = []
        for text in (label, first):
            items.append((QtCore.QPointF(x, baseline), text))
            x += metrics.horizontalAdvance(text) + 8
        rects = []
        for _ in series:
            rects.append(QtCore.QRectF(x, y - min(swatch, 10.0) / 2, swatch, min(swatch, 10.0)))
            x += step
        items.append((QtCore.QPointF(x + 6, baseline), last))
        return items, rects

    def _paint_ordinal_legend(self, painter: QtGui.QPainter) -> None:
        """Series label, then first value, one swatch per line light to dark, last value."""
        items, rects = self._ordinal_legend_items()
        hovered = self._hovered_series()
        for index, (rect, color) in enumerate(zip(rects, self._colors, strict=True)):
            painter.fillRect(rect, QtGui.QColor(color))
            if index == hovered:
                painter.setPen(QtGui.QPen(QtGui.QColor(_TEXT), 1.5))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawRect(rect.adjusted(-2, -2, 2, 2))
        painter.setPen(QtGui.QColor(_TEXT))
        for position, text in items:
            painter.drawText(position, text)

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
        QtWidgets.QToolTip.showText(
            event.globalPosition().toPoint(),
            "\n".join(self._tooltip_lines(point)),
            self,
            QtCore.QRect(),
            4000,
        )
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

    def _tooltip_lines(self, point: ChartPoint) -> list[str]:
        unit = self._rows[point.row].output_unit
        lines = []
        if self._data.series_label:
            series = next(s for s in self._data.series if point in s.points)
            lines.append(self._series_name(series))
        lines.append(f"{self._data.x_label.removesuffix(' (°)')} {point.x:g}°")
        lines.append(f"Projected area {point.y:.6g} {unit}²")
        return lines

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
