from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from cadmetrics.coordinates import AXIS_CHOICES
from cadmetrics.gui.gui_formatters import (
    component_display_groups,
    format_file_selection,
    model_info_text,
)
from cadmetrics.gui.gui_types import OperationState, ViewerOptions
from cadmetrics.gui.jobs import CalculationRequest, GuiModelPath
from cadmetrics.gui.styles import disclosure_arrow_image_urls
from cadmetrics.io import DEFAULT_BASE_TOLERANCE
from cadmetrics.sweep import SweepRange
from cadmetrics.types import ModelData

UNIT_OPTIONS = ["auto", "m", "mm", "cm", "in", "ft"]
OUTPUT_UNIT_OPTIONS = ["m", "mm", "cm", "in", "ft"]
CAMERA_DIRECTIONS = (
    ("+X", (1.0, 0.0, 0.0)),
    ("-X", (-1.0, 0.0, 0.0)),
    ("+Y", (0.0, 1.0, 0.0)),
    ("-Y", (0.0, -1.0, 0.0)),
    ("+Z", (0.0, 0.0, 1.0)),
    ("-Z", (0.0, 0.0, -1.0)),
    ("-X-Y+Z (ISO)", (-1.0, -1.0, 1.0)),
    ("+X+Y-Z (ISO)", (1.0, 1.0, -1.0)),
)


class FlexibleDoubleSpinBox(QtWidgets.QDoubleSpinBox):
    def textFromValue(self, value: float) -> str:  # noqa: N802
        text = f"{value:.{self.decimals()}f}".rstrip("0").rstrip(".")
        return text if "." in text else f"{text}.0"


class ControlPanel(QtWidgets.QWidget):
    calculation_requested = QtCore.Signal(object)
    model_reload_requested = QtCore.Signal(object)
    cancel_requested = QtCore.Signal()
    viewer_options_changed = QtCore.Signal(object)
    request_changed = QtCore.Signal(object)
    error = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._file_paths: tuple[Path, ...] = ()
        self._component_filter_path: tuple[Path, ...] | None = None
        self._component_checkboxes: list[QtWidgets.QCheckBox] = []
        self._section_toggles: dict[str, QtWidgets.QToolButton] = {}
        self._model_loaded = False
        self._advanced_dirty = False
        self.setMinimumWidth(430)
        self.setMaximumWidth(540)
        self.setObjectName("controlPanel")
        self._build()
        self.set_busy(OperationState.IDLE)
        self._set_advanced_dirty(False)

    def _build(self) -> None:
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setObjectName("controlScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QtWidgets.QWidget()
        content.setObjectName("controlContent")
        self.scroll_area.setWidget(content)
        root_layout.addWidget(self.scroll_area, 1)
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)

        setup = self._section(layout, "Setup")
        self.file_edit = QtWidgets.QLineEdit()
        self.file_edit.setPlaceholderText("STL or STEP file(s)")
        self.browse_button = QtWidgets.QPushButton("Browse")
        self.browse_button.setObjectName("secondaryButton")
        self.browse_button.clicked.connect(self._browse)
        file_row = QtWidgets.QHBoxLayout()
        file_row.setContentsMargins(0, 0, 0, 0)
        file_row.setSpacing(8)
        file_row.addWidget(self.file_edit)
        file_row.addWidget(self.browse_button)
        setup.addRow("File", file_row)
        self.input_unit = QtWidgets.QComboBox()
        self.input_unit.addItems(UNIT_OPTIONS)
        setup.addRow("Input unit", self.input_unit)
        self.output_unit = QtWidgets.QComboBox()
        self.output_unit.addItems(OUTPUT_UNIT_OPTIONS)
        setup.addRow("Output unit", self.output_unit)

        self.attitude_box = QtWidgets.QGroupBox("Attitude")
        attitude_layout = QtWidgets.QVBoxLayout(self.attitude_box)
        attitude_layout.setContentsMargins(8, 6, 8, 8)
        attitude_layout.setSpacing(5)
        self.attitude_mode = QtWidgets.QComboBox()
        self.attitude_mode.addItem("Alpha / Beta", "alpha_beta")
        self.attitude_mode.addItem("Roll / Pitch", "roll_pitch")
        self.attitude_mode.addItem("Unit vector", "vector")
        attitude_layout.addWidget(self.attitude_mode)
        self.alpha_beta_group, self.alpha_fields, self.beta_fields = self._sweep_grid(
            "Alpha", "Beta"
        )
        self.roll_pitch_group, self.roll_fields, self.pitch_fields = self._sweep_grid(
            "Roll", "Pitch"
        )
        self.vector_group, self.vector_fields = self._vector_inputs()
        attitude_layout.addWidget(self.alpha_beta_group)
        attitude_layout.addWidget(self.roll_pitch_group)
        attitude_layout.addWidget(self.vector_group)
        self.case_count = QtWidgets.QLabel("1 result")
        self.case_count.setObjectName("caseCountLabel")
        self.case_count.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        attitude_layout.addWidget(self.case_count)
        layout.addWidget(self.attitude_box)
        self.attitude_mode.currentIndexChanged.connect(self._sync_attitude_controls)
        self.attitude_mode.currentIndexChanged.connect(self._emit_preview_request)

        self.run_button = QtWidgets.QPushButton("Run Sweep")
        self.run_button.setObjectName("primaryButton")
        self.run_button.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.run_button.clicked.connect(self._run_calculation)
        self.cancel_button.clicked.connect(self.cancel_requested)
        run_row = QtWidgets.QHBoxLayout()
        run_row.setContentsMargins(0, 0, 0, 0)
        run_row.setSpacing(8)
        run_row.addWidget(self.run_button)
        run_row.addWidget(self.cancel_button)

        display = self._collapsible_widget(layout, "Shape Display")
        display_layout = QtWidgets.QGridLayout(display)
        display_layout.setContentsMargins(8, 6, 8, 6)
        display_layout.setHorizontalSpacing(12)
        display_layout.setVerticalSpacing(4)
        self.transparent_shape = self._check("Transparent", False)
        self.mesh_edges = self._check("Mesh edges", False)
        self.feature_edges = self._check("Feature edges", True)
        self.show_overlay = self._check("Overlay", True)
        self.show_projection_arrow = self._check("Projection arrow", True)
        self.show_centroid = self._check("Centroid", True)
        self.show_centroid.setToolTip("Show the centroid marker for the selected result.")
        self.show_base_face = self._check("Base face", False)
        self.show_base_face.setEnabled(False)
        self.show_newly_exposed_surface = self._check("Newly exposed surface", True)
        self.show_newly_exposed_surface.setEnabled(False)
        self.show_newly_exposed_surface.setToolTip(
            "Available when component subtraction creates newly exposed surfaces."
        )
        self.detailed_overlay = self._check("Detailed overlay", False)
        self.detailed_overlay.setToolTip(
            "Show geometry bounds, calculation metadata, and diagnostic values in the 3D view."
        )
        self.camera_direction = QtWidgets.QComboBox()
        for label, direction in CAMERA_DIRECTIONS:
            self.camera_direction.addItem(label, direction)
        self.camera_direction.setCurrentIndex(6)
        self.save_image_button = QtWidgets.QPushButton("Save Image")
        self.save_image_button.setObjectName("secondaryButton")
        for widget in (
            self.transparent_shape,
            self.mesh_edges,
            self.feature_edges,
            self.show_overlay,
            self.show_projection_arrow,
            self.show_centroid,
            self.show_base_face,
            self.show_newly_exposed_surface,
            self.detailed_overlay,
        ):
            widget.toggled.connect(self._emit_viewer_options)
        self.camera_direction.currentIndexChanged.connect(self._emit_viewer_options)
        display_layout.addWidget(self.transparent_shape, 0, 0)
        display_layout.addWidget(self.mesh_edges, 0, 1)
        display_layout.addWidget(self.feature_edges, 1, 0)
        display_layout.addWidget(self.show_overlay, 1, 1)
        display_layout.addWidget(self.show_projection_arrow, 2, 0)
        display_layout.addWidget(self.show_base_face, 2, 1)
        display_layout.addWidget(self.show_centroid, 3, 0)
        display_layout.addWidget(self.detailed_overlay, 3, 1)
        display_layout.addWidget(self.show_newly_exposed_surface, 4, 0, 1, 2)
        display_layout.addWidget(QtWidgets.QLabel("Camera"), 5, 0)
        display_layout.addWidget(self.camera_direction, 5, 1)
        display_layout.addWidget(self.save_image_button, 6, 0, 1, 2)

        advanced = self._collapsible(layout, "Advanced")
        self.axis_x = self._axis_combo("x")
        self.axis_y = self._axis_combo("y")
        self.axis_z = self._axis_combo("z")
        axis_row = QtWidgets.QHBoxLayout()
        axis_row.setContentsMargins(0, 0, 0, 0)
        axis_row.setSpacing(6)
        for label, combo in (("X", self.axis_x), ("Y", self.axis_y), ("Z", self.axis_z)):
            axis_row.addWidget(QtWidgets.QLabel(label))
            axis_row.addWidget(combo)
        advanced.addRow("Axis map", axis_row)

        component_widget = QtWidgets.QWidget()
        component_layout = QtWidgets.QVBoxLayout(component_widget)
        component_layout.setContentsMargins(0, 0, 0, 0)
        component_layout.setSpacing(6)
        self.component_summary = QtWidgets.QLabel("Load a multi-solid STEP file.")
        component_layout.addWidget(self.component_summary)
        component_list = QtWidgets.QWidget()
        self.component_list_layout = QtWidgets.QVBoxLayout(component_list)
        self.component_list_layout.setContentsMargins(0, 0, 0, 0)
        self.component_list_layout.setSpacing(2)
        self.component_scroll = QtWidgets.QScrollArea()
        self.component_scroll.setWidgetResizable(True)
        self.component_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.component_scroll.setMinimumHeight(130)
        self.component_scroll.setMaximumHeight(130)
        self.component_scroll.setWidget(component_list)
        component_layout.addWidget(self.component_scroll)
        component_buttons = QtWidgets.QHBoxLayout()
        component_buttons.setContentsMargins(0, 0, 0, 0)
        component_buttons.setSpacing(6)
        self.component_all_button = QtWidgets.QPushButton("All")
        self.component_none_button = QtWidgets.QPushButton("None")
        self.component_all_button.setObjectName("secondaryButton")
        self.component_none_button.setObjectName("secondaryButton")
        self.component_all_button.clicked.connect(lambda: self._set_all_components(True))
        self.component_none_button.clicked.connect(lambda: self._set_all_components(False))
        component_buttons.addWidget(self.component_all_button)
        component_buttons.addWidget(self.component_none_button)
        component_buttons.addStretch(1)
        component_layout.addLayout(component_buttons)
        advanced.addRow("Components", component_widget)

        self.step_component_mode = QtWidgets.QComboBox()
        self.step_component_mode.addItem("Filter OFF (default)", "filter")
        self.step_component_mode.addItem("Subtract OFF", "subtract")
        advanced.addRow("Component mode", self.step_component_mode)

        self.step_metrics = QtWidgets.QComboBox()
        self.step_metrics.addItem("B-Rep (default)", "brep")
        self.step_metrics.addItem("Mesh", "mesh")
        advanced.addRow("STEP metrics", self.step_metrics)
        self.mesh_deflection = FlexibleDoubleSpinBox()
        self.mesh_deflection.setRange(1.0e-8, 1.0)
        self.mesh_deflection.setDecimals(8)
        self.mesh_deflection.setValue(1.0e-3)
        self.mesh_deflection_auto = self._check("Auto", True)
        self.mesh_deflection_auto.toggled.connect(
            lambda checked: self.mesh_deflection.setEnabled(not checked)
        )
        mesh_row = QtWidgets.QHBoxLayout()
        mesh_row.setContentsMargins(0, 0, 0, 0)
        mesh_row.setSpacing(8)
        mesh_row.addWidget(self.mesh_deflection)
        mesh_row.addWidget(self.mesh_deflection_auto)
        advanced.addRow("Mesh deflection", mesh_row)
        self.angular_deflection = FlexibleDoubleSpinBox()
        self.angular_deflection.setRange(1.0e-6, 1.0)
        self.angular_deflection.setValue(0.1)
        advanced.addRow("Angular deflection", self.angular_deflection)
        self.base_tolerance = FlexibleDoubleSpinBox()
        self.base_tolerance.setRange(1.0e-12, 1.0)
        self.base_tolerance.setDecimals(12)
        self.base_tolerance.setValue(DEFAULT_BASE_TOLERANCE)
        advanced.addRow("Base tolerance", self.base_tolerance)
        self.apply_advanced_button = QtWidgets.QPushButton("Reload Model with Settings")
        self.apply_advanced_button.clicked.connect(self._apply_advanced_settings)
        self.advanced_status = QtWidgets.QLabel("Changes not applied")
        self.advanced_status.setObjectName("dirtyStatusLabel")
        self.advanced_status.setVisible(False)
        advanced.addRow(self.advanced_status)
        advanced.addRow(self.apply_advanced_button)

        model_details = self._collapsible(layout, "Model Details")
        self.model_info = QtWidgets.QTextEdit()
        self.model_info.setReadOnly(True)
        self.model_info.setPlaceholderText("Load a model to inspect geometry details.")
        self.model_info.setMinimumHeight(150)
        self.model_info.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        model_details.addRow(self.model_info)
        layout.addStretch(1)

        action_bar = QtWidgets.QWidget()
        action_bar.setObjectName("actionBar")
        action_layout = QtWidgets.QVBoxLayout(action_bar)
        action_layout.setContentsMargins(12, 9, 12, 11)
        action_layout.setSpacing(6)
        self.operation_label = QtWidgets.QLabel()
        self.operation_label.setObjectName("operationLabel")
        self.operation_label.setVisible(False)
        self.model_summary = QtWidgets.QLabel("No model loaded")
        self.model_summary.setObjectName("modelSummaryLabel")
        self.model_summary.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        action_layout.addWidget(self.operation_label)
        action_layout.addWidget(self.model_summary)
        action_layout.addLayout(run_row)
        root_layout.addWidget(action_bar)

        self.run_button.setToolTip("Run the configured attitude sweep.")
        self.cancel_button.setToolTip("Stop the sweep after the current case finishes.")
        self.component_all_button.setToolTip(
            "Available after loading a STEP file with multiple components."
        )
        self.component_none_button.setToolTip(
            "Available after loading a STEP file with multiple components."
        )
        self._connect_advanced_dirty_signals()
        self._sync_attitude_controls()
        self.mesh_deflection.setEnabled(False)
        self._sync_case_count()

    @property
    def file_paths(self) -> tuple[Path, ...]:
        text = self.file_edit.text().strip()
        if self._file_paths and text == format_file_selection(self._file_paths):
            return self._file_paths
        if not text:
            raise ValueError("Select one or more model files.")
        return (Path(text).expanduser(),)

    def set_file_paths(self, paths: tuple[Path, ...]) -> None:
        self._file_paths = tuple(path.expanduser() for path in paths)
        self.file_edit.setText(format_file_selection(self._file_paths))
        self.file_edit.setToolTip("\n".join(str(path) for path in self._file_paths))

    def request(self) -> CalculationRequest:
        paths = self.file_paths
        for path in paths:
            if not path.exists():
                raise ValueError(f"File does not exist: {path}")
        model_path: GuiModelPath = paths[0] if len(paths) == 1 else paths
        alpha_start, alpha_end, alpha_step = (field.value() for field in self.alpha_fields)
        beta_start, beta_end, beta_step = (field.value() for field in self.beta_fields)
        roll_start, roll_end, roll_step = (field.value() for field in self.roll_fields)
        pitch_start, pitch_end, pitch_step = (field.value() for field in self.pitch_fields)
        vector_x, vector_y, vector_z = (field.value() for field in self.vector_fields)
        return CalculationRequest(
            file=model_path,
            attitude_mode=self.attitude_mode.currentData(),
            input_unit=self.input_unit.currentText(),
            output_unit=self.output_unit.currentText(),
            mesh_deflection=(
                "auto" if self.mesh_deflection_auto.isChecked() else self.mesh_deflection.value()
            ),
            angular_deflection=self.angular_deflection.value(),
            base_tolerance=self.base_tolerance.value(),
            axis_map=",".join(
                (self.axis_x.currentData(), self.axis_y.currentData(), self.axis_z.currentData())
            ),
            step_metric_source=self.step_metrics.currentData(),
            step_components=self._selected_components(paths),
            step_component_mode=self.step_component_mode.currentData(),
            roll_start=roll_start,
            roll_end=roll_end,
            roll_step=roll_step,
            alpha_start=alpha_start,
            alpha_end=alpha_end,
            alpha_step=alpha_step,
            beta_start=beta_start,
            beta_end=beta_end,
            beta_step=beta_step,
            pitch_start=pitch_start,
            pitch_end=pitch_end,
            pitch_step=pitch_step,
            vector_x=vector_x,
            vector_y=vector_y,
            vector_z=vector_z,
        )

    def viewer_options(self) -> ViewerOptions:
        return ViewerOptions(
            transparent_shape=self.transparent_shape.isChecked(),
            mesh_edges=self.mesh_edges.isChecked(),
            feature_edges=self.feature_edges.isChecked(),
            show_projection_arrow=self.show_projection_arrow.isChecked(),
            show_centroid=self.show_centroid.isChecked(),
            show_base_face=self.show_base_face.isChecked(),
            show_newly_exposed_surface=self.show_newly_exposed_surface.isChecked(),
            show_overlay=self.show_overlay.isChecked(),
            detailed_overlay=self.detailed_overlay.isChecked(),
            camera_direction=tuple(self.camera_direction.currentData()),
        )

    def set_busy(self, state: OperationState) -> None:
        busy = state is not OperationState.IDLE
        for widget in (
            self.file_edit,
            self.browse_button,
            self.input_unit,
            self.output_unit,
            self.attitude_box,
            self.step_component_mode,
        ):
            widget.setEnabled(not busy)
        for checkbox in self._component_checkboxes:
            checkbox.setEnabled(not busy)
        self.run_button.setEnabled(not busy)
        self.apply_advanced_button.setEnabled(not busy and self._advanced_dirty)
        cancellable = state in (OperationState.CALCULATING, OperationState.CANCELLING)
        self.cancel_button.setVisible(cancellable)
        self.cancel_button.setEnabled(state is OperationState.CALCULATING)
        messages = {
            OperationState.LOADING: "Loading model…",
            OperationState.CALCULATING: "Calculating sweep… Cancel stops after the current case.",
            OperationState.CANCELLING: "Finishing the current geometry operation…",
        }
        self.operation_label.setText(messages.get(state, ""))
        self.operation_label.setVisible(busy)
        self._sync_component_controls(not busy and bool(self._component_checkboxes))

    def set_model(self, model: ModelData) -> None:
        self._model_loaded = True
        self.model_info.setText(model_info_text(model))
        component_text = ""
        if model.component_names:
            component_text = (
                f" · {len(model.selected_components)}/{len(model.component_names)} components"
            )
        self.model_summary.setText(
            f"{model.path.name} · {model.source_format.upper()}{component_text}"
        )
        self.model_summary.setToolTip(str(model.path))
        self._populate_components(model)
        self._set_advanced_dirty(False)

    def set_operation_message(self, message: str) -> None:
        self.operation_label.setText(message)
        self.operation_label.setVisible(bool(message))

    def _browse(self) -> None:
        names, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Open CAD file(s)", "", "CAD Files (*.stl *.step *.stp);;All Files (*)"
        )
        if not names:
            return
        self.set_file_paths(tuple(Path(name) for name in names))
        self._clear_components()
        if self._emit_request(self.model_reload_requested):
            self._set_advanced_dirty(False)

    def _emit_request(self, signal: QtCore.SignalInstance) -> bool:
        try:
            request = self.request()
        except Exception as exc:
            self.error.emit(str(exc))
            return False
        signal.emit(request)
        return True

    def _run_calculation(self) -> None:
        if self._emit_request(self.calculation_requested):
            self._set_advanced_dirty(False)

    def _apply_advanced_settings(self) -> None:
        if self._emit_request(self.model_reload_requested):
            self._set_advanced_dirty(False)

    def _emit_viewer_options(self) -> None:
        self.viewer_options_changed.emit(self.viewer_options())

    def _emit_preview_request(self) -> None:
        try:
            request = self.request()
        except Exception:
            return
        self.request_changed.emit(request)

    def _populate_components(self, model: ModelData) -> None:
        current = set(self._selected_components(self.file_paths) or ())
        self._clear_component_widgets()
        self._component_filter_path = self.file_paths
        if len(model.component_names) <= 1:
            self.component_summary.setText(
                "Single STEP component."
                if model.source_format == "step"
                else "Component filters are available for STEP files."
            )
            self._sync_component_controls(False)
            return
        selected = set(model.selected_components) or current
        for group_name, components in component_display_groups(
            model.component_names, grouped=model.is_assembly and model.source_format == "step"
        ):
            if group_name:
                self.component_list_layout.addWidget(QtWidgets.QLabel(group_name))
            for index, name in components:
                checkbox = QtWidgets.QCheckBox(f"{index}: {name}")
                checkbox.setProperty("component_index", index)
                checkbox.setChecked(index in selected)
                checkbox.toggled.connect(self._sync_component_summary)
                checkbox.toggled.connect(self._mark_advanced_dirty)
                self.component_list_layout.addWidget(checkbox)
                self._component_checkboxes.append(checkbox)
        self.component_list_layout.addStretch(1)
        self._sync_component_summary()
        self._sync_component_controls(True)

    def _selected_components(self, paths: tuple[Path, ...]) -> tuple[int, ...] | None:
        if not self._component_checkboxes or paths != self._component_filter_path:
            return None
        selected = tuple(
            int(box.property("component_index"))
            for box in self._component_checkboxes
            if box.isChecked()
        )
        if not selected:
            raise ValueError("Select at least one STEP component.")
        return selected

    def _clear_components(self) -> None:
        self._component_filter_path = None
        self._clear_component_widgets()
        self.component_summary.setText("Load a multi-solid STEP file.")
        self._sync_component_controls(False)

    def _clear_component_widgets(self) -> None:
        self._component_checkboxes = []
        while self.component_list_layout.count():
            item = self.component_list_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

    def _set_all_components(self, checked: bool) -> None:
        for checkbox in self._component_checkboxes:
            checkbox.setChecked(checked)
        self._sync_component_summary()

    def _sync_component_summary(self) -> None:
        total = len(self._component_checkboxes)
        selected = sum(box.isChecked() for box in self._component_checkboxes)
        if total:
            self.component_summary.setText(f"{selected} of {total} components enabled.")

    def _sync_component_controls(self, enabled: bool) -> None:
        self.component_all_button.setEnabled(enabled)
        self.component_none_button.setEnabled(enabled)

    def _sync_attitude_controls(self) -> None:
        mode = self.attitude_mode.currentData()
        self.alpha_beta_group.setVisible(mode == "alpha_beta")
        self.roll_pitch_group.setVisible(mode == "roll_pitch")
        self.vector_group.setVisible(mode == "vector")
        self._sync_sweep_inputs()

    def _sync_sweep_inputs(self) -> None:
        for fields in (
            self.alpha_fields,
            self.beta_fields,
            self.roll_fields,
            self.pitch_fields,
        ):
            is_range = fields[0].value() != fields[1].value()
            fields[2].setToolTip(
                "Increment between sweep values."
                if is_range
                else "Ignored when Start and End are the same."
            )
        self._sync_case_count()

    def _sync_case_count(self) -> None:
        mode = self.attitude_mode.currentData()
        if mode == "vector":
            count = 1
        else:
            groups = (
                (self.roll_fields, self.pitch_fields)
                if mode == "roll_pitch"
                else (self.alpha_fields, self.beta_fields)
            )
            try:
                count = 1
                for fields in groups:
                    count *= SweepRange(*(field.value() for field in fields)).count
            except ValueError:
                self.case_count.setText("Check sweep values")
                self.case_count.setProperty("invalid", True)
                self.case_count.style().unpolish(self.case_count)
                self.case_count.style().polish(self.case_count)
                return
        self.case_count.setProperty("invalid", False)
        self.case_count.setText(f"{count:,} result{'s' if count != 1 else ''}")
        self.case_count.style().unpolish(self.case_count)
        self.case_count.style().polish(self.case_count)

    @staticmethod
    def _sweep_spec(start: float, end: float, step: float) -> str:
        return SweepRange(start, end, step).spec

    def _connect_advanced_dirty_signals(self) -> None:
        for combo in (
            self.axis_x,
            self.axis_y,
            self.axis_z,
            self.step_component_mode,
            self.step_metrics,
        ):
            combo.currentIndexChanged.connect(self._mark_advanced_dirty)
        for field in (
            self.mesh_deflection,
            self.angular_deflection,
            self.base_tolerance,
        ):
            field.valueChanged.connect(self._mark_advanced_dirty)
        self.mesh_deflection_auto.toggled.connect(self._mark_advanced_dirty)

    def _mark_advanced_dirty(self, *_args: object) -> None:
        self._set_advanced_dirty(True)

    def _set_advanced_dirty(self, dirty: bool) -> None:
        self._advanced_dirty = dirty and self._model_loaded
        self.advanced_status.setVisible(self._advanced_dirty)
        self.apply_advanced_button.setEnabled(
            self._advanced_dirty and self.run_button.isEnabled()
        )
        self.apply_advanced_button.setToolTip(
            "Reload the model using the changed axis, component, and tessellation settings."
            if self._model_loaded
            else "Load a model before reloading it with Advanced settings."
        )
        toggle = self._section_toggles.get("Advanced")
        if toggle is not None:
            toggle.setText(
                "Advanced · changes not applied" if self._advanced_dirty else "Advanced"
            )

    def _section(self, parent: QtWidgets.QVBoxLayout, title: str) -> QtWidgets.QFormLayout:
        box = QtWidgets.QGroupBox(title)
        form = QtWidgets.QFormLayout(box)
        self._configure_form_layout(form, margins=(8, 6, 8, 7))
        parent.addWidget(box)
        return form

    def _collapsible_widget(self, parent: QtWidgets.QVBoxLayout, title: str) -> QtWidgets.QWidget:
        right_arrow, down_arrow = disclosure_arrow_image_urls()
        section = QtWidgets.QWidget()
        section.setObjectName("collapsibleSection")
        section_layout = QtWidgets.QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(3)

        toggle = QtWidgets.QToolButton(section)
        toggle.setText(title)
        toggle.setCheckable(True)
        toggle.setChecked(False)
        toggle.setObjectName("sectionToggle")
        toggle.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setArrowType(QtCore.Qt.ArrowType.NoArrow)
        toggle.setIcon(QtGui.QIcon(right_arrow))
        toggle.setIconSize(QtCore.QSize(10, 10))
        toggle.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        content = QtWidgets.QGroupBox(section)
        content.setObjectName("sectionContent")
        content.setVisible(False)
        self._section_toggles[title] = toggle

        def sync_collapsed_state(checked: bool) -> None:
            toggle.setIcon(QtGui.QIcon(down_arrow if checked else right_arrow))
            content.setVisible(checked)

        toggle.toggled.connect(sync_collapsed_state)
        section_layout.addWidget(toggle)
        section_layout.addWidget(content)
        parent.addWidget(section)
        return content

    def _collapsible(self, parent: QtWidgets.QVBoxLayout, title: str) -> QtWidgets.QFormLayout:
        content = self._collapsible_widget(parent, title)
        form = QtWidgets.QFormLayout(content)
        self._configure_form_layout(form, margins=(8, 8, 8, 8))
        return form

    def _sweep_grid(
        self, first_label: str, second_label: str
    ) -> tuple[
        QtWidgets.QWidget,
        tuple[FlexibleDoubleSpinBox, FlexibleDoubleSpinBox, FlexibleDoubleSpinBox],
        tuple[FlexibleDoubleSpinBox, FlexibleDoubleSpinBox, FlexibleDoubleSpinBox],
    ]:
        widget = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        for column, text in enumerate(("Start", "End", "Step"), start=1):
            header = QtWidgets.QLabel(text)
            header.setStyleSheet("color: #5f6872;")
            header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(header, 0, column)
        first = self._sweep_row(grid, 1, first_label)
        second = self._sweep_row(grid, 2, second_label)
        grid.setColumnStretch(0, 0)
        for column in (1, 2, 3):
            grid.setColumnStretch(column, 1)
        return widget, first, second

    def _sweep_row(
        self, grid: QtWidgets.QGridLayout, row: int, label: str
    ) -> tuple[FlexibleDoubleSpinBox, FlexibleDoubleSpinBox, FlexibleDoubleSpinBox]:
        row_label = QtWidgets.QLabel(label)
        row_label.setStyleSheet("color: #374151;")
        row_label.setMinimumWidth(46)
        grid.addWidget(row_label, row, 0)
        fields = (self._number(0.0), self._number(0.0), self._number(1.0))
        for column, field in enumerate(fields, start=1):
            grid.addWidget(field, row, column)
            field.valueChanged.connect(self._emit_preview_request)
            field.valueChanged.connect(self._sync_sweep_inputs)
        return fields

    def _vector_inputs(
        self,
    ) -> tuple[
        QtWidgets.QWidget,
        tuple[FlexibleDoubleSpinBox, FlexibleDoubleSpinBox, FlexibleDoubleSpinBox],
    ]:
        widget = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        fields = (self._number(1.0), self._number(0.0), self._number(0.0))
        for column, (label, field) in enumerate(zip(("X", "Y", "Z"), fields, strict=True)):
            header = QtWidgets.QLabel(label)
            header.setStyleSheet("color: #5f6872;")
            header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(header, 0, column)
            grid.addWidget(field, 1, column)
            grid.setColumnStretch(column, 1)
            field.valueChanged.connect(self._emit_preview_request)
        return widget, fields

    def _number(self, value: float) -> FlexibleDoubleSpinBox:
        field = FlexibleDoubleSpinBox()
        field.setRange(-1.0e6, 1.0e6)
        field.setDecimals(6)
        field.setSingleStep(1.0)
        field.setValue(value)
        field.setMinimumWidth(70)
        return field

    def _axis_combo(self, default: str) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        combo.setMinimumWidth(62)
        for axis in AXIS_CHOICES:
            combo.addItem(axis.upper(), axis)
        combo.setCurrentIndex(combo.findData(default))
        return combo

    def _check(self, text: str, checked: bool) -> QtWidgets.QCheckBox:
        checkbox = QtWidgets.QCheckBox(text)
        checkbox.setChecked(checked)
        return checkbox

    @staticmethod
    def _configure_form_layout(
        form: QtWidgets.QFormLayout,
        *,
        margins: tuple[int, int, int, int],
    ) -> None:
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(10)
        form.setContentsMargins(*margins)
