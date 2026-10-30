"""Results of a cross-section calculation: summary, table, and S(x) or S'(x) chart."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from cadmetrics.csv_io import SECTION_CSV_FIELDS, write_rows_csv
from cadmetrics.gui.gui_formatters import format_cell
from cadmetrics.gui.results_chart import (
    DETAIL_COLOR,
    IMAGE_SUFFIXES,
    MAX_SERIES,
    REFERENCE_COLOR,
    ChartData,
    ChartLine,
    ChartPoint,
    ChartSeries,
    LegendEntry,
    ResultsChart,
    series_colors,
)
from cadmetrics.gui.table_copy import (
    TableCopyActions,
    configure_row_selection,
    full_precision,
    tsv,
)
from cadmetrics.result_schema import SECTION_FIELD_SPECS, ResultFieldSpec
from cadmetrics.sections import CrossSectionResult, SectionRow, SectionSeries
from cadmetrics.types import FloatArray

STALE_MESSAGE = "Results are out of date — Run Sections to update."
EMPTY_MESSAGE = "The chart needs a cross-section result."
# What the chart plots: section area or its slope dArea/dX against x, the wave drag of
# each sine term, or the wave drag of each roll angle.
AREA = "area"
SLOPE = "slope"
TERMS = "terms"
ROLL_ANGLES = "roll_angles"
_Y_TITLES = {
    AREA: "Section area",
    SLOPE: "dArea/dX",
    TERMS: "Wave drag D/q per term",
    ROLL_ANGLES: "Wave drag D/q",
}
_BAR_FILL = 0.7  # Share of each term's slot that its bar fills.

# Columns shown first, then the rest in CSV order.
_GUI_SPECS: tuple[ResultFieldSpec, ...] = tuple(
    spec
    for _, spec in sorted(
        enumerate(SECTION_FIELD_SPECS),
        key=lambda item: (
            item[1].gui_priority is None,
            item[1].gui_priority if item[1].gui_priority is not None else item[0],
        ),
    )
)
SECTION_DISPLAY_FIELDS = [spec.key for spec in _GUI_SPECS]
_UNIT_POWERS = {
    "x": 1,
    "area_slope": 1,
    "fitted_area_slope": 1,
    "sears_haack_area_slope": 1,
    "area": 2,
    "sears_haack_area": 2,
    "wave_drag_area": 2,
    "sears_haack_drag_area": 2,
    "mean_wave_drag_area": 2,
}
_UNIT_SUFFIXES = {1: "", 2: "²", 3: "³"}
_DISPLAY_ROLE = int(QtCore.Qt.ItemDataRole.DisplayRole)
_TOOLTIP_ROLE = int(QtCore.Qt.ItemDataRole.ToolTipRole)
_ALIGNMENT_ROLE = int(QtCore.Qt.ItemDataRole.TextAlignmentRole)
_LEFT = QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
_RIGHT = QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
DEFAULT_COLUMN_WIDTH = 120


def section_header_label(key: str, output_unit: str | None) -> str:
    spec = next(spec for spec in _GUI_SPECS if spec.key == key)
    power = _UNIT_POWERS.get(key)
    if power is None or not output_unit:
        return spec.gui_label
    return f"{spec.gui_label} ({output_unit}{_UNIT_SUFFIXES[power]})"


def section_rows_to_tsv(rows: Sequence[SectionRow]) -> str:
    """Serialize sections as tab-separated text with headers and 12 significant digits."""
    unit = rows[0].output_unit if rows else None
    return tsv(
        [section_header_label(key, unit) for key in SECTION_DISPLAY_FIELDS],
        ([spec.extract_value(row) for spec in _GUI_SPECS] for row in rows),
    )


def section_summary_text(result: CrossSectionResult) -> str:
    """One line of key values: largest area, wave drag, and the volume check."""
    unit = result.model.output_unit
    largest = max(result.series, key=lambda series: series.max_area)
    parts = [
        f"Max area {format_cell(largest.max_area)} {unit}² at x = "
        f"{format_cell(largest.max_area_x)} {unit}"
    ]
    drag = result.wave_drag_area
    reference = result.sears_haack_drag_area
    if drag is not None:
        label = "Wave drag D/q" if len(result.series) == 1 else "Mean wave drag D/q"
        text = f"{label} {format_cell(drag)} {unit}²"
        if reference:
            text += f" ({format_cell(drag / reference)} × Sears-Haack)"
        parts.append(text)
    integral = sum(series.weight * series.volume for series in result.series)
    volume_text = f"∫S dx {format_cell(integral)} {unit}³"
    if result.model.volume:
        volume_text += f" (model volume {format_cell(result.model.volume)} {unit}³)"
    parts.append(volume_text)
    return "  ·  ".join(parts)


class SectionTableModel(QtCore.QAbstractTableModel):
    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[SectionRow] = []

    @property
    def output_unit(self) -> str | None:
        return self._rows[0].output_unit if self._rows else None

    def row(self, index: int) -> SectionRow:
        return self._rows[index]

    def set_rows(self, rows: list[SectionRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(  # noqa: N802
        self,
        parent: QtCore.QModelIndex | QtCore.QPersistentModelIndex = QtCore.QModelIndex(),
    ) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(  # noqa: N802
        self,
        parent: QtCore.QModelIndex | QtCore.QPersistentModelIndex = QtCore.QModelIndex(),
    ) -> int:
        return 0 if parent.isValid() else len(_GUI_SPECS)

    def data(
        self,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        role: int = _DISPLAY_ROLE,
    ) -> object | None:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        if role not in {_DISPLAY_ROLE, _TOOLTIP_ROLE, _ALIGNMENT_ROLE}:
            return None
        value = _GUI_SPECS[index.column()].extract_value(self._rows[index.row()])
        if role == _ALIGNMENT_ROLE:
            numeric = isinstance(value, int | float) and not isinstance(value, bool)
            return _RIGHT if numeric else _LEFT
        if role == _TOOLTIP_ROLE:
            return f"{value:.12g}" if isinstance(value, float) else format_cell(value)
        return format_cell(value)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = _DISPLAY_ROLE,
    ) -> object | None:
        if orientation != QtCore.Qt.Orientation.Horizontal or not 0 <= section < len(_GUI_SPECS):
            return None
        spec = _GUI_SPECS[section]
        if role == _DISPLAY_ROLE:
            return section_header_label(spec.key, self.output_unit)
        if role == _TOOLTIP_ROLE:
            return f"{spec.description}\n{spec.gui_tooltip}"
        return None


def section_chart_data(
    rows: Sequence[SectionRow], *, quantity: str = AREA, theta: float | None = None
) -> ChartData:
    """One line per roll angle (a single line at Mach 1) against x.

    ``quantity`` plots the area, or the fitted slope the wave drag is computed from.
    ``theta`` keeps the line of one roll angle; ``None`` keeps them all.
    """
    if quantity not in {AREA, SLOPE}:
        raise ValueError(f"Section rows chart area or slope, not {quantity!r}")
    unit = rows[0].output_unit if rows else ""
    x_label = f"X ({unit})" if unit else "X"
    groups: dict[float | None, list[ChartPoint]] = {}
    for index, row in enumerate(rows):
        if theta is not None and row.theta_deg != theta:
            continue
        y = row.area if quantity == AREA else row.fitted_area_slope
        groups.setdefault(row.theta_deg, []).append(ChartPoint(row.x, y, index))
    if not groups:
        return ChartData(x_label, None, (), EMPTY_MESSAGE)
    if len(groups) > MAX_SERIES:
        return ChartData(
            x_label,
            None,
            (),
            f"{len(groups)} roll angles are too many lines to compare; the chart shows up to "
            f"{MAX_SERIES}. Choose one roll angle, use the table, or calculate fewer roll angles.",
        )
    multiple = len(groups) > 1
    series = tuple(
        ChartSeries(theta if multiple else None, tuple(points))
        for theta, points in sorted(groups.items(), key=lambda item: item[0] or 0.0)
    )
    return ChartData(x_label, "Theta" if multiple else None, series)


def term_chart_data(result: CrossSectionResult | None, *, theta: float | None = None) -> ChartData:
    """The wave drag of each sine term, of one roll angle or averaged over all of them.

    The points are no table rows; their ``row`` is minus the term number.
    """
    spectrum = _spectrum(result, theta)
    if spectrum is None:
        return ChartData("Term n", None, (), "The wave drag needs at least 4 sections.")
    points = tuple(
        ChartPoint(float(n), float(value), -n) for n, value in enumerate(spectrum, start=1)
    )
    return ChartData("Term n", None, (ChartSeries(None, points),))


def roll_angle_chart_data(result: CrossSectionResult | None) -> ChartData:
    """The wave drag of each roll angle; each point is the row with that roll angle's max area."""
    if result is None or len(result.series) < 2:
        return ChartData("Theta (°)", None, (), "Above Mach 1, each roll angle has a wave drag.")
    points = []
    offset = 0
    for series in result.series:
        drag = series.wave_drag_area
        if drag is not None and series.theta_deg is not None:
            row = offset + int(np.argmax(series.area))
            points.append(ChartPoint(series.theta_deg, drag, row))
        offset += series.x.shape[0]
    if len(points) < 2:
        return ChartData("Theta (°)", None, (), "The wave drag needs at least 4 sections.")
    ordered = tuple(sorted(points, key=lambda point: point.x))
    return ChartData("Theta (°)", None, (ChartSeries(None, ordered),))


def _series_for(result: CrossSectionResult | None, theta: float | None) -> SectionSeries | None:
    if result is None:
        return None
    if theta is None:
        return result.series[0] if len(result.series) == 1 else None
    return next((series for series in result.series if series.theta_deg == theta), None)


def _spectrum(result: CrossSectionResult | None, theta: float | None) -> FloatArray | None:
    if result is None:
        return None
    if theta is None:
        return result.wave_drag_spectrum
    series = _series_for(result, theta)
    return series.wave_drag_spectrum if series is not None else None


class SectionsChart(ResultsChart):
    """Sections against x, or wave drag by term or roll angle.

    Click a point of a section or roll angle to show that section in the 3D view.
    """

    y_title = _Y_TITLES[AREA]
    show_markers = False

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._result: CrossSectionResult | None = None
        self._section_rows: list[SectionRow] = []
        self._show_reference = True
        self._quantity = AREA
        self._theta: float | None = None

    @property
    def quantity(self) -> str:
        return self._quantity

    @property
    def can_show_reference(self) -> bool:
        """Whether a Sears-Haack reference can be drawn for what is shown."""
        if self._quantity == ROLL_ANGLES:
            return bool(self._data.series)
        if self._quantity == TERMS:
            return self._sears_haack_drag() is not None
        return len(self._data.series) == 1

    def set_result(self, result: CrossSectionResult | None) -> None:
        self._result = result
        self._section_rows = result.rows() if result is not None else []
        self._rows = self._section_rows  # type: ignore[assignment]
        self._refresh()

    def set_quantity(self, quantity: str) -> None:
        if quantity not in _Y_TITLES:
            raise ValueError(f"Unknown section chart quantity: {quantity!r}")
        if quantity != self._quantity:
            self._quantity = quantity
            self.y_title = _Y_TITLES[quantity]
            self.show_markers = quantity == ROLL_ANGLES
            self._refresh()

    def set_theta(self, theta: float | None) -> None:
        """Show the line of one roll angle, or every line with ``None``."""
        if theta != self._theta:
            self._theta = theta
            self._refresh()

    def set_show_reference(self, show: bool) -> None:
        if show != self._show_reference:
            self._show_reference = show
            self.update()

    def _refresh(self) -> None:
        if self._quantity == TERMS:
            self._data = term_chart_data(self._result, theta=self._theta)
        elif self._quantity == ROLL_ANGLES:
            self._data = roll_angle_chart_data(self._result)
        else:
            self._data = section_chart_data(
                self._section_rows, quantity=self._quantity, theta=self._theta
            )
        self._colors = series_colors(len(self._data.series))
        if self._selected is not None and self._selected >= len(self._section_rows):
            self._selected = None
        self._hovered = None
        self.update()

    def _y_unit(self) -> str:
        unit = self._section_rows[0].output_unit if self._section_rows else ""
        suffix = "" if self._quantity == SLOPE else "²"
        return f" ({unit}{suffix})" if unit else ""

    def _sears_haack_drag(self) -> float | None:
        """D/q of the Sears-Haack body (or the mean of them) shown with the terms."""
        if self._theta is None and self._result is not None:
            return self._result.sears_haack_drag_area
        series = _series_for(self._result, self._theta)
        return series.sears_haack_drag_area if series is not None else None

    # Overlays and legend ------------------------------------------------------------

    def _single_line_rows(self) -> list[SectionRow]:
        # Overlays belong to one equivalent body; with several roll angles each has its own
        # length, and their Sears-Haack curves would not be comparable.
        if self._quantity not in {AREA, SLOPE} or len(self._data.series) != 1:
            return []
        return [self._section_rows[point.row] for point in self._data.series[0].points]

    def _overlay_lines(self) -> list[ChartLine]:
        if self._quantity == ROLL_ANGLES:
            return self._roll_angle_lines()
        rows = self._single_line_rows()
        if not rows:
            return []
        lines = []
        if self._quantity == SLOPE:
            # Finite differences show steps and tessellation noise the fitted series
            # leaves out; they are clipped instead of squeezing the fitted line.
            lines.append(
                ChartLine(
                    tuple((row.x, row.area_slope) for row in rows),
                    DETAIL_COLOR,
                    "Differences",
                    width=1.0,
                    scales_axis=False,
                )
            )
        if self._show_reference:
            lines.append(
                ChartLine(
                    tuple(
                        (
                            row.x,
                            row.sears_haack_area
                            if self._quantity == AREA
                            else row.sears_haack_area_slope,
                        )
                        for row in rows
                    ),
                    REFERENCE_COLOR,
                    "Sears-Haack",
                    dashed=True,
                )
            )
        return lines

    def _roll_angle_lines(self) -> list[ChartLine]:
        result = self._result
        if result is None or not self._data.series:
            return []
        points = self._data.series[0].points
        lines = []
        if self._show_reference:
            by_theta = {series.theta_deg: series for series in result.series}
            reference = tuple(
                (point.x, drag)
                for point in points
                if (drag := by_theta[point.x].sears_haack_drag_area) is not None
            )
            lines.append(ChartLine(reference, REFERENCE_COLOR, "Sears-Haack", dashed=True))
        mean = result.wave_drag_area
        if mean is not None:
            ends = ((points[0].x, mean), (points[-1].x, mean))
            lines.append(ChartLine(ends, DETAIL_COLOR, "Mean", width=1.0))
        return lines

    def _extra_y_values(self) -> list[float]:
        drag = self._sears_haack_drag() if self._quantity == TERMS else None
        return [drag] if drag is not None and self._show_reference else []

    def _legend_entries(self) -> list[LegendEntry]:
        if self._quantity in {TERMS, ROLL_ANGLES}:
            if not self._data.series:
                return []
            name = "D/q" if self._quantity == ROLL_ANGLES else "D/q per term"
            if self._quantity == TERMS and self._theta is not None:
                name += f", Theta {self._theta:g}°"
            elif self._quantity == TERMS and self._result and len(self._result.series) > 1:
                name += ", mean of the roll angles"
            entries = [LegendEntry(self._colors[0], name)]
            if self._quantity == TERMS and self._extra_y_values():
                entries.append(LegendEntry(REFERENCE_COLOR, "Sears-Haack", dashed=True))
            entries += [
                LegendEntry(line.color, line.label or "", line.dashed)
                for line in self._overlay_lines()
                if line.label
            ]
            return entries
        overlays = [line for line in self._overlay_lines() if line.label]
        if not overlays:
            return super()._legend_entries()
        name = "Area" if self._quantity == AREA else "Fitted"
        if self._theta is not None:
            name += f", Theta {self._theta:g}°"
        return [
            LegendEntry(self._colors[0], name),
            *(LegendEntry(line.color, line.label or "", line.dashed) for line in overlays),
        ]

    # Terms are bars -----------------------------------------------------------------

    def _x_extent(self, xs: list[float]) -> tuple[float, float]:
        if self._quantity == TERMS:
            return 0.5, max(xs) + 0.5
        return super()._x_extent(xs)

    def _x_ticks(self, low: float, high: float) -> list[float]:
        if self._quantity != TERMS:
            return super()._x_ticks(low, high)
        count = int(high)
        step = next(step for step in (1, 2, 5, 10) if count / step <= 10)
        return [1.0, *(float(n) for n in range(step, count + 1, step) if n > 1)]

    def _bar_rect(self, n: float, value: float, fill: float = _BAR_FILL) -> QtCore.QRectF:
        x0, x1 = self._x_range
        half = fill / 2 * self._plot.width() / (x1 - x0)
        top = self._map_xy(n, value)
        bottom = self._map_xy(n, 0.0)
        return QtCore.QRectF(top.x() - half, top.y(), 2 * half, bottom.y() - top.y())

    def point_at(self, position: QtCore.QPointF) -> ChartPoint | None:
        if self._quantity != TERMS:
            return super().point_at(position)
        if not self._data.series or not self._plot.top() <= position.y() <= self._plot.bottom():
            return None
        for point in self._data.series[0].points:
            rect = self._bar_rect(point.x, point.y)
            if rect.left() <= position.x() <= rect.right():
                return point
        return None

    def _paint_series(self, painter: QtGui.QPainter) -> None:
        if self._quantity != TERMS:
            super()._paint_series(painter)
            return
        color = QtGui.QColor(self._colors[0])
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        for point in self._data.series[0].points:
            painter.setBrush(color.darker(130) if point.row == self._hovered else color)
            painter.drawRect(self._bar_rect(point.x, point.y))
        drag = self._extra_y_values()
        if drag:
            # The Sears-Haack body has a single term, n = 2.
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(
                QtGui.QPen(QtGui.QColor(REFERENCE_COLOR), 1.5, QtCore.Qt.PenStyle.DashLine)
            )
            painter.drawRect(self._bar_rect(2.0, drag[0], fill=0.95))

    def _point_for_row(self, row: int | None) -> tuple[int, ChartPoint] | None:
        if self._quantity == ROLL_ANGLES and row is not None and 0 <= row < len(self._section_rows):
            # Any section of a roll angle stands for that roll angle's point.
            theta = self._section_rows[row].theta_deg
            for point in self._data.series[0].points if self._data.series else ():
                if point.x == theta:
                    return 0, point
            return None
        return super()._point_for_row(row)

    # Tooltips -----------------------------------------------------------------------

    def _tooltip_lines(self, point: ChartPoint) -> list[str]:
        unit = self._section_rows[0].output_unit if self._section_rows else ""
        if self._quantity == TERMS:
            return self._term_tooltip(point, unit)
        if self._quantity == ROLL_ANGLES:
            return self._roll_angle_tooltip(point, unit)
        row = self._section_rows[point.row]
        reference = bool(self._single_line_rows()) and self._show_reference
        lines = []
        if row.theta_deg is not None:
            lines.append(f"Theta {row.theta_deg:g}°")
        lines.append(f"x {row.x:.6g} {unit}")
        if self._quantity == AREA:
            lines.append(f"Area {row.area:.6g} {unit}²")
            if reference:
                lines.append(f"Sears-Haack {row.sears_haack_area:.6g} {unit}²")
        else:
            lines.append(f"Fitted dArea/dX {row.fitted_area_slope:.6g} {unit}")
            lines.append(f"Differences {row.area_slope:.6g} {unit}")
            if reference:
                lines.append(f"Sears-Haack {row.sears_haack_area_slope:.6g} {unit}")
        return lines

    def _term_tooltip(self, point: ChartPoint, unit: str) -> list[str]:
        values = [p.y for p in self._data.series[0].points]
        total = sum(values)
        n = int(point.x)
        cumulative = sum(values[:n])
        lines = [f"Term n = {n}"]
        share = f" ({point.y / total:.0%})" if total > 0 else ""
        lines.append(f"D/q {point.y:.6g} {unit}²{share}")
        if n > 1:
            share = f" ({cumulative / total:.0%})" if total > 0 else ""
            lines.append(f"Terms 1-{n} {cumulative:.6g} {unit}²{share}")
        drag = self._extra_y_values()
        if n == 2 and drag:
            lines.append(f"Sears-Haack {drag[0]:.6g} {unit}²")
        return lines

    def _roll_angle_tooltip(self, point: ChartPoint, unit: str) -> list[str]:
        lines = [f"Theta {point.x:g}°", f"D/q {point.y:.6g} {unit}²"]
        result = self._result
        series = _series_for(result, point.x)
        if result is not None and series is not None:
            mean = result.wave_drag_area
            if mean:
                total = sum(s.weight for s in result.series)
                lines.append(f"Share of mean {series.weight * point.y / total / mean:.0%}")
            if series.sears_haack_drag_area is not None and self._show_reference:
                lines.append(f"Sears-Haack {series.sears_haack_drag_area:.6g} {unit}²")
        return lines


def theta_choices(result: CrossSectionResult) -> list[tuple[str, float | None]]:
    """Roll-angle choices for the chart: every line, then each one with its wave drag.

    Each roll angle shows its D/q and its share of the mean D/q, which also counts its
    weight; the roll angles with the largest share are the ones to improve first.
    """
    if len(result.series) < 2:
        return []
    unit = result.model.output_unit
    mean = result.wave_drag_area
    shares = [
        series.weight * series.wave_drag_area / mean
        if series.wave_drag_area is not None and mean
        else None
        for series in result.series
    ]
    largest = max((share for share in shares if share is not None), default=None)
    choices: list[tuple[str, float | None]] = [("All", None)]
    for series, share in sorted(
        zip(result.series, shares, strict=True), key=lambda item: item[0].theta_deg or 0.0
    ):
        text = f"{series.theta_deg:g}°"
        if series.wave_drag_area is not None:
            text += f"  D/q {format_cell(series.wave_drag_area)} {unit}²"
        if share is not None and largest is not None:
            text += f", {share:.0%} of mean"
            if math.isclose(share, largest, rel_tol=1e-9):
                text += " (largest)"
        choices.append((text, series.theta_deg))
    return choices


class SectionsPanel(QtWidgets.QWidget):
    """Table, chart, and summary of one cross-section calculation."""

    selected_row_changed = QtCore.Signal(object)
    rows_changed = QtCore.Signal()
    error = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._result: CrossSectionResult | None = None
        self._rows: list[SectionRow] = []
        self._protected_paths: tuple[Path, ...] = ()
        self._busy = False
        self._busy_title = "Calculating…"
        self._stale = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QtWidgets.QWidget()
        toolbar.setObjectName("resultToolbar")
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 6, 10, 6)
        self.result_count = QtWidgets.QLabel("Sections: 0")
        self.result_count.setObjectName("resultCountLabel")
        self.table_view_button = self._view_toggle("Table", "Show the sections as a table.")
        self.chart_view_button = self._view_toggle("Chart", "Plot the sections against x.")
        self.chart_view_button.setChecked(True)
        view_group = QtWidgets.QButtonGroup(self)
        view_group.setExclusive(True)
        view_group.addButton(self.table_view_button)
        view_group.addButton(self.chart_view_button)
        self.chart_view_button.toggled.connect(lambda _checked: self._sync())
        self.area_view_button = self._view_toggle("Area", "Plot section area against x.")
        self.slope_view_button = self._view_toggle(
            "Slope",
            "Plot dArea/dX against x: the smooth series the wave drag is computed from, "
            "over the finite differences of the sections (gray). Kinks show up as steps, "
            "and narrow bumps as sharp swings.",
        )
        self.terms_view_button = self._view_toggle(
            "Terms",
            "Plot the wave drag of each sine term of the slope. Term 1 carries the base area, "
            "term 2 the overall size (all of a Sears-Haack body), and higher terms the local "
            "shape: kinks, bumps, and steps.",
        )
        self.roll_angles_view_button = self._view_toggle(
            "Roll angles",
            "Plot the wave drag of each roll angle, with its Sears-Haack body and the mean. "
            "Click a point to choose that roll angle.",
        )
        self.area_view_button.setChecked(True)
        self._quantity_buttons = {
            self.area_view_button: AREA,
            self.slope_view_button: SLOPE,
            self.terms_view_button: TERMS,
            self.roll_angles_view_button: ROLL_ANGLES,
        }
        quantity_group = QtWidgets.QButtonGroup(self)
        quantity_group.setExclusive(True)
        for button in self._quantity_buttons:
            quantity_group.addButton(button)
        quantity_group.buttonToggled.connect(self._quantity_toggled)
        self.theta_label = QtWidgets.QLabel("Roll angle")
        self.theta_combo = QtWidgets.QComboBox()
        self.theta_combo.setObjectName("sectionThetaCombo")
        # The closed list shows the angle and D/q; the open list is wide enough for the rest.
        self.theta_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.theta_combo.setMinimumContentsLength(16)
        self.theta_combo.setToolTip(
            "Show every roll angle, or one equivalent body with its Sears-Haack reference. "
            "Each roll angle is listed with its wave drag D/q."
        )
        self.theta_combo.currentIndexChanged.connect(self._theta_changed)
        self.sears_haack_check = QtWidgets.QCheckBox("Sears-Haack")
        self.sears_haack_check.setChecked(True)
        self.sears_haack_check.setToolTip(
            "Overlay the minimum-wave-drag body with the same length and volume (dashed)."
        )
        self.sears_haack_check.toggled.connect(self._sears_haack_toggled)
        self.stale_label = QtWidgets.QLabel(STALE_MESSAGE)
        self.stale_label.setObjectName("resultsStaleLabel")
        self.stale_label.setVisible(False)
        self.save_image_button = QtWidgets.QPushButton("Save Image")
        self.save_image_button.setObjectName("secondaryButton")
        self.save_image_button.setToolTip("Save the chart as a PNG or SVG image.")
        self.save_image_button.clicked.connect(self.choose_image_path)
        self.save_button = QtWidgets.QPushButton("Save CSV")
        self.save_button.setObjectName("secondaryButton")
        self.save_button.clicked.connect(self.choose_csv_path)
        toolbar_layout.addWidget(self.result_count)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(self.table_view_button)
        toolbar_layout.addWidget(self.chart_view_button)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(self.stale_label)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.save_image_button)
        toolbar_layout.addWidget(self.save_button)
        layout.addWidget(toolbar)

        # What the chart plots gets its own row, so the results area stays narrow.
        self.chart_options = QtWidgets.QWidget()
        self.chart_options.setObjectName("chartOptions")
        options_layout = QtWidgets.QHBoxLayout(self.chart_options)
        options_layout.setContentsMargins(10, 0, 10, 4)
        for button in self._quantity_buttons:
            options_layout.addWidget(button)
        options_layout.addSpacing(12)
        options_layout.addWidget(self.theta_label)
        options_layout.addWidget(self.theta_combo)
        options_layout.addSpacing(12)
        options_layout.addWidget(self.sears_haack_check)
        options_layout.addStretch(1)
        layout.addWidget(self.chart_options)

        self.summary_label = QtWidgets.QLabel()
        self.summary_label.setObjectName("sectionSummaryLabel")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.warning_label = QtWidgets.QLabel()
        self.warning_label.setObjectName("sectionWarningLabel")
        self.warning_label.setWordWrap(True)
        summary_box = QtWidgets.QWidget()
        summary_layout = QtWidgets.QVBoxLayout(summary_box)
        summary_layout.setContentsMargins(10, 6, 10, 4)
        summary_layout.setSpacing(4)
        summary_layout.addWidget(self.summary_label)
        summary_layout.addWidget(self.warning_label)
        self.summary_box = summary_box
        layout.addWidget(summary_box)

        self.stack = QtWidgets.QStackedWidget()
        self.empty_state = QtWidgets.QWidget()
        empty_layout = QtWidgets.QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(24, 24, 24, 24)
        empty_layout.addStretch(1)
        self.empty_title = QtWidgets.QLabel("No sections yet")
        self.empty_title.setObjectName("emptyStateTitle")
        self.empty_title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.empty_message = QtWidgets.QLabel(
            "Run Sections to calculate the cross-sectional area distribution."
        )
        self.empty_message.setObjectName("emptyStateMessage")
        self.empty_message.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_message)
        empty_layout.addStretch(1)
        self.stack.addWidget(self.empty_state)

        self.chart = SectionsChart()
        self.chart.row_clicked.connect(self._chart_row_clicked)
        self.table = QtWidgets.QTableView()
        self.table.setProperty("stale", False)
        self._table_model = SectionTableModel(self.table)
        self.table.setModel(self._table_model)
        header = self.table.horizontalHeader()
        header.setDefaultSectionSize(DEFAULT_COLUMN_WIDTH)
        header.setMinimumSectionSize(70)
        self.table.setAlternatingRowColors(True)
        self._cocoa_cell_selection = configure_row_selection(self.table)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        for column, key in enumerate(SECTION_DISPLAY_FIELDS):
            if key == "file":
                self.table.setColumnHidden(column, True)
        self.table.selectionModel().currentRowChanged.connect(self._emit_selected_row)
        self.copy_actions = TableCopyActions(
            self.table,
            copy_value=self.copy_value,
            copy_row=self.copy_selection,
            copy_all=self.copy_all_rows,
        )
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.chart)
        layout.addWidget(self.stack, 1)
        self._sync()

    @property
    def result(self) -> CrossSectionResult | None:
        return self._result

    @property
    def rows(self) -> list[SectionRow]:
        return list(self._rows)

    @property
    def is_stale(self) -> bool:
        return self._stale

    @property
    def can_save(self) -> bool:
        return not self._busy and bool(self._rows)

    def set_result(
        self,
        result: CrossSectionResult | None,
        *,
        protected_paths: Iterable[str | Path] | None = None,
    ) -> None:
        self._result = result
        self._rows = result.rows() if result is not None else []
        if protected_paths is not None:
            self._protected_paths = tuple(Path(path) for path in protected_paths)
        self._table_model.set_rows(list(self._rows))
        self.chart.set_selected(None)
        if self.roll_angles_view_button.isChecked() and (result is None or len(result.series) < 2):
            self.area_view_button.setChecked(True)
        self.chart.set_result(result)
        self.theta_combo.blockSignals(True)
        self.theta_combo.clear()
        for text, theta in theta_choices(result) if result is not None else []:
            self.theta_combo.addItem(text, theta)
        metrics = self.theta_combo.fontMetrics()
        texts = [self.theta_combo.itemText(index) for index in range(self.theta_combo.count())]
        widest = max((metrics.horizontalAdvance(text) for text in texts), default=0)
        self.theta_combo.view().setMinimumWidth(widest + 40)
        self.theta_combo.blockSignals(False)
        self.chart.set_theta(None)
        self._set_stale(False)
        self._sync()

    def clear(self) -> None:
        self.set_result(None)

    def mark_stale(self, stale: bool = True) -> None:
        stale = stale and bool(self._rows)
        if stale and not self._stale:
            self.table.selectionModel().clearSelection()
            self.table.setCurrentIndex(QtCore.QModelIndex())
            self.chart.set_selected(None)
        self._set_stale(stale)

    def set_busy(self, busy: bool, *, title: str = "Calculating…") -> None:
        self._busy = busy
        self._busy_title = title
        self._sync()

    def has_selection(self) -> bool:
        return self.selected_row() is not None

    def selected_row(self) -> SectionRow | None:
        current = self.table.currentIndex()
        if not current.isValid() or not 0 <= current.row() < len(self._rows):
            return None
        return self._rows[current.row()]

    def select_row(self, index: int) -> None:
        if 0 <= index < len(self._rows):
            if self._cocoa_cell_selection:
                column = next(
                    c
                    for c in range(len(SECTION_DISPLAY_FIELDS))
                    if not self.table.isColumnHidden(c)
                )
                self.table.setCurrentIndex(self._table_model.index(index, column))
            else:
                self.table.selectRow(index)

    def select_max_area(self) -> None:
        """Select the station with the largest area, a useful first section to look at."""
        if self._rows:
            best = max(range(len(self._rows)), key=lambda index: self._rows[index].area)
            self.select_row(best)

    def copy_value(self, index: QtCore.QModelIndex | QtCore.QPersistentModelIndex) -> None:
        """Copy one cell at full precision."""
        if index.isValid() and 0 <= index.row() < len(self._rows):
            value = _GUI_SPECS[index.column()].extract_value(self._rows[index.row()])
            QtWidgets.QApplication.clipboard().setText(full_precision(value))

    def copy_selection(self) -> None:
        row = self.selected_row()
        if row is not None:
            QtWidgets.QApplication.clipboard().setText(section_rows_to_tsv([row]))

    def copy_all_rows(self) -> None:
        if self._rows:
            QtWidgets.QApplication.clipboard().setText(section_rows_to_tsv(self._rows))

    def save_csv(self, path: str | Path) -> None:
        if not self._rows:
            raise ValueError("No section results to save.")
        write_rows_csv(
            path, self._rows, protected_paths=self._protected_paths, fields=SECTION_CSV_FIELDS
        )

    def choose_csv_path(self) -> None:
        if not self._rows:
            self.error.emit("No section results to save.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save CSV", "cadmetrics_sections.csv", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            self.save_csv(path)
        except Exception as exc:
            self.error.emit(str(exc))

    def choose_image_path(self) -> None:
        path, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Chart Image",
            "cadmetrics_sections.png",
            "PNG Image (*.png);;SVG Image (*.svg)",
        )
        if not path:
            return
        if Path(path).suffix.lower() not in IMAGE_SUFFIXES:
            path += ".svg" if selected_filter.startswith("SVG") else ".png"
        try:
            self.chart.save_image(path)
        except Exception as exc:
            self.error.emit(str(exc))

    @staticmethod
    def _view_toggle(text: str, tooltip: str) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setObjectName("viewButton")
        button.setText(text)
        button.setToolTip(tooltip)
        button.setCheckable(True)
        return button

    def _sears_haack_toggled(self, checked: bool) -> None:
        self.chart.set_show_reference(checked)

    def _quantity_toggled(self, button: QtWidgets.QAbstractButton, checked: bool) -> None:
        if checked:
            self.chart.set_quantity(self._quantity_buttons[button])  # type: ignore[index]
            self._sync()

    def _chart_row_clicked(self, index: int) -> None:
        if self.chart.quantity == ROLL_ANGLES and 0 <= index < len(self._rows):
            self.theta_combo.setCurrentIndex(self.theta_combo.findData(self._rows[index].theta_deg))
        self.select_row(index)

    def _theta_changed(self, _index: int) -> None:
        self.chart.set_theta(self.theta_combo.currentData())
        self._sync()

    def _emit_selected_row(
        self, current: QtCore.QModelIndex, _previous: QtCore.QModelIndex
    ) -> None:
        if not current.isValid() or not 0 <= current.row() < len(self._rows):
            return
        theta = self._rows[current.row()].theta_deg
        if self.theta_combo.currentData() not in {None, theta}:
            # A row of another roll angle switches the chart to that roll angle's line.
            self.theta_combo.setCurrentIndex(self.theta_combo.findData(theta))
        self.chart.set_selected(current.row())
        self.selected_row_changed.emit(self._rows[current.row()])

    def _set_stale(self, stale: bool) -> None:
        if stale == self._stale:
            return
        self._stale = stale
        self.stale_label.setVisible(stale)
        self.chart.set_stale(stale)
        self.table.setProperty("stale", stale)
        style = self.table.style()
        style.unpolish(self.table)
        style.polish(self.table)
        self.table.viewport().update()
        self._sync()

    def _sync(self) -> None:
        rows = bool(self._rows)
        result = self._result
        sections = result.section_count if result is not None else 0
        angles = len(result.series) if result is not None else 0
        self.result_count.setText(
            f"Sections: {sections:,}" + (f" × {angles} roll angles" if angles > 1 else "")
        )
        self.save_button.setEnabled(self.can_save)
        self.save_button.setToolTip(
            "Save every section to CSV." if rows else "Run Sections before saving results."
        )
        chart_shown = rows and self.chart_view_button.isChecked()
        self.save_image_button.setVisible(chart_shown)
        self.save_image_button.setEnabled(not self._busy and bool(self.chart.data.series))
        self.chart_options.setVisible(chart_shown)
        self.roll_angles_view_button.setVisible(chart_shown and angles > 1)
        self.theta_label.setVisible(chart_shown and angles > 1)
        self.theta_combo.setVisible(chart_shown and angles > 1)
        self.sears_haack_check.setVisible(chart_shown and self.chart.can_show_reference)
        self.summary_box.setVisible(result is not None)
        if result is not None:
            self.summary_label.setText(section_summary_text(result))
            warnings = "\n".join(result.warnings)
            self.warning_label.setText(warnings)
            self.warning_label.setVisible(bool(warnings))
        if rows:
            self.stack.setCurrentWidget(self.chart if chart_shown else self.table)
        else:
            if self._busy:
                self.empty_title.setText(self._busy_title)
                self.empty_message.setText("The sections will appear here when they are done.")
            else:
                self.empty_title.setText("No sections yet")
                self.empty_message.setText(
                    "Run Sections to calculate the cross-sectional area distribution."
                )
            self.stack.setCurrentWidget(self.empty_state)
        self.rows_changed.emit()
