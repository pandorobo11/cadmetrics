"""Results of a cross-section calculation: summary, table, and S(x) chart."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from cadmetrics.csv_io import SECTION_CSV_FIELDS, write_rows_csv
from cadmetrics.gui.gui_formatters import format_cell
from cadmetrics.gui.results_chart import (
    IMAGE_SUFFIXES,
    MAX_SERIES,
    ChartData,
    ChartPoint,
    ChartSeries,
    ResultsChart,
    series_colors,
)
from cadmetrics.result_schema import SECTION_FIELD_SPECS, ResultFieldSpec
from cadmetrics.sections import CrossSectionResult, SectionRow

STALE_MESSAGE = "Results are out of date — Run Sections to update."
EMPTY_MESSAGE = "The chart needs a cross-section result."

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


def section_chart_data(rows: Sequence[SectionRow]) -> ChartData:
    """One line per roll angle (a single line at Mach 1), area against x."""
    unit = rows[0].output_unit if rows else ""
    x_label = f"X ({unit})" if unit else "X"
    groups: dict[float | None, list[ChartPoint]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(row.theta_deg, []).append(ChartPoint(row.x, row.area, index))
    if not groups:
        return ChartData(x_label, None, (), EMPTY_MESSAGE)
    if len(groups) > MAX_SERIES:
        return ChartData(
            x_label,
            None,
            (),
            f"{len(groups)} roll angles are too many lines to compare; the chart shows up to "
            f"{MAX_SERIES}. Use the table, or calculate fewer roll angles.",
        )
    multiple = len(groups) > 1
    series = tuple(
        ChartSeries(theta if multiple else None, tuple(points))
        for theta, points in sorted(groups.items(), key=lambda item: item[0] or 0.0)
    )
    return ChartData(x_label, "Theta" if multiple else None, series)


class SectionsChart(ResultsChart):
    """Section area against x; click a point to show that section in the 3D view."""

    y_title = "Section area"
    show_markers = False

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._section_rows: list[SectionRow] = []
        self._show_reference = True

    def set_section_rows(self, rows: Sequence[SectionRow]) -> None:
        self._section_rows = list(rows)
        self._rows = self._section_rows  # type: ignore[assignment]
        self._refresh()

    def set_show_reference(self, show: bool) -> None:
        if show != self._show_reference:
            self._show_reference = show
            self.update()

    def _refresh(self) -> None:
        self._data = section_chart_data(self._section_rows)
        self._colors = series_colors(len(self._data.series))
        if self._selected is not None and self._selected >= len(self._section_rows):
            self._selected = None
        self._hovered = None
        self.update()

    def _reference_points(self) -> list[tuple[float, float]]:
        # The Sears-Haack body is drawn for a single equivalent body only; with several
        # roll angles each has its own length, and the lines would not be comparable.
        if not self._show_reference or len(self._data.series) != 1:
            return []
        return [(row.x, row.sears_haack_area) for row in self._section_rows]

    def _tooltip_lines(self, point: ChartPoint) -> list[str]:
        row = self._section_rows[point.row]
        unit = row.output_unit
        lines = []
        if row.theta_deg is not None:
            lines.append(f"Theta {row.theta_deg:g}°")
        lines.append(f"x {row.x:.6g} {unit}")
        lines.append(f"Area {row.area:.6g} {unit}²")
        if self._reference_points():
            lines.append(f"Sears-Haack {row.sears_haack_area:.6g} {unit}²")
        return lines


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
        self.chart_view_button = self._view_toggle("Chart", "Plot section area against x.")
        self.chart_view_button.setChecked(True)
        view_group = QtWidgets.QButtonGroup(self)
        view_group.setExclusive(True)
        view_group.addButton(self.table_view_button)
        view_group.addButton(self.chart_view_button)
        self.chart_view_button.toggled.connect(lambda _checked: self._sync())
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
        toolbar_layout.addWidget(self.sears_haack_check)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(self.stale_label)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.save_image_button)
        toolbar_layout.addWidget(self.save_button)
        layout.addWidget(toolbar)

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
        self.chart.row_clicked.connect(self.select_row)
        self.table = QtWidgets.QTableView()
        self.table.setProperty("stale", False)
        self._table_model = SectionTableModel(self.table)
        self.table.setModel(self._table_model)
        header = self.table.horizontalHeader()
        header.setDefaultSectionSize(DEFAULT_COLUMN_WIDTH)
        header.setMinimumSectionSize(70)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        for column, key in enumerate(SECTION_DISPLAY_FIELDS):
            if key == "file":
                self.table.setColumnHidden(column, True)
        self.table.selectionModel().currentRowChanged.connect(self._emit_selected_row)
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
        self.chart.set_section_rows(self._rows)
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
            self.table.selectRow(index)

    def select_max_area(self) -> None:
        """Select the station with the largest area, a useful first section to look at."""
        if self._rows:
            best = max(range(len(self._rows)), key=lambda index: self._rows[index].area)
            self.select_row(best)

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

    def _emit_selected_row(
        self, current: QtCore.QModelIndex, _previous: QtCore.QModelIndex
    ) -> None:
        if not current.isValid() or not 0 <= current.row() < len(self._rows):
            return
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
        single_series = result is not None and len(result.series) == 1
        self.sears_haack_check.setVisible(chart_shown and single_series)
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
