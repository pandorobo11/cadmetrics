from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6 import QtCore, QtGui, QtWidgets

from cadmetrics.gui.control_panel import ControlPanel
from cadmetrics.gui.gui_types import OperationState
from cadmetrics.types import ModelData


def _model(path: Path, names: tuple[str, ...] = (), fmt: str = "step") -> ModelData:
    return ModelData(
        path=path,
        source_format=fmt,
        vertices=np.empty((0, 3), dtype=float),
        faces=np.empty((0, 3), dtype=np.int64),
        input_unit="m",
        output_unit="m",
        volume=1.0,
        surface_area=6.0,
        base_area=1.0,
        is_watertight=True,
        component_names=names,
        selected_components=tuple(range(1, len(names) + 1)),
    )


def _panel(qtbot, tmp_path: Path, name: str = "model.stl") -> ControlPanel:
    panel = ControlPanel()
    qtbot.addWidget(panel)
    path = tmp_path / name
    path.touch()
    panel.set_file_paths((path,))
    return panel


def test_multi_file_summary_lists_all_names(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path)
    model = _model(Path("a.step;b.step"), ("A", "B"))
    panel.set_model(model)
    assert panel.model_summary.text().startswith("a.step + b.step · STEP")


def test_run_disabled_with_message_when_inputs_invalid(qtbot, tmp_path: Path) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)
    assert panel.run_button.isEnabled() is False
    assert panel.validation_label.objectName() == "validationMessageLabel"
    assert panel.validation_label.isHidden() is False

    panel.file_edit.setText(str(tmp_path / "missing.stl"))
    assert panel.run_button.isEnabled() is False
    assert "does not exist" in panel.validation_label.text()

    panel = _panel(qtbot, tmp_path)
    assert panel.run_button.isEnabled() is True
    assert panel.validation_label.isHidden() is True

    panel.alpha_fields[0].setValue(0.0)
    panel.alpha_fields[1].setValue(10.0)
    panel.alpha_fields[2].setValue(0.0)
    assert panel.run_button.isEnabled() is False
    assert "sweep" in panel.validation_label.text().lower()
    panel.alpha_fields[2].setValue(5.0)
    assert panel.run_button.isEnabled() is True


def test_zero_vector_disables_run(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path)
    panel.attitude_mode.setCurrentIndex(panel.attitude_mode.findData("vector"))
    for field in panel.vector_fields:
        field.setValue(0.0)
    assert panel.run_button.isEnabled() is False
    assert "(0, 0, 0)" in panel.validation_label.text()
    panel.vector_fields[2].setValue(1.0)
    assert panel.run_button.isEnabled() is True


def test_no_selected_components_disables_run(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path, "asm.step")
    panel.set_model(_model(tmp_path / "asm.step", ("A", "B")))
    panel.component_none_button.click()
    assert panel.run_button.isEnabled() is False
    assert "component" in panel.validation_label.text()
    panel.component_all_button.click()
    assert panel.run_button.isEnabled() is True


def test_busy_state_respects_validation(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path)
    panel.set_busy(OperationState.CALCULATING)
    assert panel.run_button.isEnabled() is False
    panel.set_busy(OperationState.IDLE)
    assert panel.run_button.isEnabled() is True
    panel.file_edit.clear()
    panel.set_busy(OperationState.LOADING)
    panel.set_busy(OperationState.IDLE)
    assert panel.run_button.isEnabled() is False


def test_enter_in_file_field_requests_model_load(qtbot, tmp_path: Path) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)
    path = tmp_path / "typed.stl"
    path.touch()
    requests = []
    panel.model_reload_requested.connect(requests.append)
    panel.file_edit.setText(str(path))
    assert requests == []
    qtbot.keyClick(panel.file_edit, QtCore.Qt.Key.Key_Return)
    assert len(requests) == 1
    assert requests[0].file == path

    panel.file_edit.setText(str(tmp_path / "missing.stl"))
    qtbot.keyClick(panel.file_edit, QtCore.Qt.Key.Key_Return)
    assert len(requests) == 1


def test_advanced_wording_explains_run_sweep_applies(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path)
    panel.set_model(_model(tmp_path / "model.stl", fmt="stl"))
    panel.axis_x.setCurrentIndex(panel.axis_x.findData("-x"))
    assert "next Run Sweep" in panel.advanced_status.text()
    assert panel.apply_advanced_button.text() == "Apply && Reload"
    assert "not applied" not in panel._section_toggles["Advanced"].text()
    assert "pending" in panel._section_toggles["Advanced"].text()


def test_components_section_is_independent_and_opens_for_multiple(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path, "asm.step")
    advanced_content = panel._section_toggles["Advanced"].parentWidget()
    assert not advanced_content.isAncestorOf(panel.component_summary)
    assert not advanced_content.isAncestorOf(panel.step_component_mode)
    toggle = panel._section_toggles["Components"]
    assert toggle.isChecked() is False

    panel.set_model(_model(tmp_path / "asm.step", ("A", "B")))
    assert toggle.isChecked() is True
    assert panel.component_detail.isHidden() is False
    assert 0 < panel.component_scroll.maximumHeight() <= 200


def test_single_component_shows_one_line_only(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path)
    panel.set_model(_model(tmp_path / "model.stl", fmt="stl"))
    assert panel.component_detail.isHidden() is True
    assert panel.component_summary.text()


def test_component_mode_labels(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)
    combo = panel.step_component_mode
    assert combo.itemData(0) == "filter" and combo.itemData(1) == "subtract"
    assert combo.itemText(0) == "Exclude unchecked (default)"
    assert combo.itemText(1) == "Subtract unchecked"
    assert combo.toolTip()


def test_shape_display_groups_and_no_empty_cells(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)
    grid = panel.show_grid.parentWidget().layout()
    labels = [
        grid.itemAt(i).widget().text()
        for i in range(grid.count())
        if grid.itemAt(i).widget().objectName() == "subheadingLabel"
    ]
    assert labels == ["Rendering", "Annotations"]
    occupied = set()
    for i in range(grid.count()):
        row, col, rs, cs = grid.getItemPosition(i)
        for r in range(row, row + rs):
            for c in range(col, col + cs):
                occupied.add((r, c))
    assert occupied == {(r, c) for r in range(grid.rowCount()) for c in range(3)}


def test_axis_map_combos_fit_the_longest_axis_label(qtbot) -> None:
    from cadmetrics.gui.styles import application_stylesheet

    panel = ControlPanel()
    qtbot.addWidget(panel)
    panel.setStyleSheet(application_stylesheet())
    panel._section_toggles["Advanced"].setChecked(True)
    panel.resize(panel.minimumWidth(), 900)
    panel.show()
    qtbot.waitExposed(panel)
    for combo in (panel.axis_x, panel.axis_y, panel.axis_z):
        # Text padding (7px) plus the 26px drop-down area must leave room for "-Z".
        assert combo.width() >= combo.fontMetrics().horizontalAdvance("-Z") + 7 + 26


def test_all_fields_share_one_left_and_right_edge(qtbot) -> None:
    from cadmetrics.gui.styles import application_stylesheet

    panel = ControlPanel()
    qtbot.addWidget(panel)
    panel.setStyleSheet(application_stylesheet())
    for title in ("Components", "Advanced"):
        panel._section_toggles[title].setChecked(True)
    panel.component_detail.setVisible(True)
    panel.resize(440, 1600)
    panel.show()
    qtbot.waitExposed(panel)
    content = panel.scroll_area.widget()

    def edges(widget) -> tuple[int, int]:
        left = widget.mapTo(content, QtCore.QPoint(0, 0)).x()
        return left, left + widget.width()

    fields = {
        name: getattr(panel, name)
        for name in (
            "input_unit",
            "output_unit",
            "attitude_mode",
            "step_component_mode",
            "step_metrics",
            "mesh_quality",
            "base_tolerance",
        )
    }
    field_edges = {name: edges(field) for name, field in fields.items()}
    label_edges = {
        label.text(): (edges(label), label.isVisible())
        for label in content.findChildren(QtWidgets.QLabel, "fieldLabel")
    }
    assert len(set(field_edges.values())) == 1, (field_edges, label_edges)
    left, right = edges(panel.input_unit)
    assert edges(panel.file_edit)[0] == left
    assert edges(panel.browse_button)[1] == right
    assert edges(panel.alpha_fields[0])[0] == left
    assert edges(panel.alpha_fields[2])[1] == right
    assert edges(panel.axis_z)[1] == right
    labels = [
        label for label in content.findChildren(QtWidgets.QLabel, "fieldLabel") if label.isVisible()
    ]
    assert len({edges(label)[0] for label in labels}) == 1


def test_unavailable_checkboxes_have_tooltips(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)
    assert panel.show_base_face.isEnabled() is False
    assert panel.show_base_face.toolTip()
    assert panel.show_newly_exposed_surface.isEnabled() is False
    assert "Unavailable" in panel.show_newly_exposed_surface.toolTip()


def _wheel(widget) -> QtGui.QWheelEvent:
    center = QtCore.QPointF(widget.rect().center())
    return QtGui.QWheelEvent(
        center,
        widget.mapToGlobal(center),
        QtCore.QPoint(0, 0),
        QtCore.QPoint(0, 120),
        QtCore.Qt.MouseButton.NoButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
        QtCore.Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def test_wheel_over_unfocused_inputs_scrolls_instead_of_editing(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path)
    spin = panel.alpha_fields[1]
    combo = panel.output_unit
    for widget in (spin, combo):
        assert widget.focusPolicy() == QtCore.Qt.FocusPolicy.StrongFocus

    event = _wheel(spin)
    QtWidgets.QApplication.sendEvent(spin, event)
    assert not event.isAccepted()
    assert spin.value() == 0.0

    event = _wheel(combo)
    QtWidgets.QApplication.sendEvent(combo, event)
    assert not event.isAccepted()
    assert combo.currentText() == "m"


def test_angle_fields_show_degrees_and_no_field_has_step_buttons(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path)
    for field in (*panel.alpha_fields, *panel.beta_fields, *panel.roll_fields):
        assert field.suffix() == "°"
    panel.alpha_fields[1].setValue(90.0)
    assert panel.alpha_fields[1].text() == "90.0°"
    assert all(field.suffix() == "" for field in panel.vector_fields)

    no_buttons = QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
    spin_boxes = panel.findChildren(QtWidgets.QDoubleSpinBox)
    assert len(spin_boxes) >= 18
    assert all(field.buttonSymbols() == no_buttons for field in spin_boxes)
    for field in (panel.mesh_deflection, panel.angular_deflection, panel.base_tolerance):
        assert field.toolTip()

    # Keyboard stepping still works once a field has focus.
    field = panel.alpha_fields[2]
    field.setFocus()
    qtbot.keyClick(field, QtCore.Qt.Key.Key_Up)
    assert field.value() == 2.0


def test_buttons_match_input_height_and_open_sections_have_no_gap(qtbot, tmp_path: Path) -> None:
    from cadmetrics.gui.styles import application_stylesheet

    panel = _panel(qtbot, tmp_path)
    panel.setStyleSheet(application_stylesheet())
    panel.resize(440, 900)
    panel.show()
    qtbot.waitExposed(panel)
    height = panel.file_edit.height()
    for widget in (panel.browse_button, panel.input_unit, panel.alpha_fields[0], panel.run_button):
        assert widget.height() == height == 34
    # Hidden until a multi-component model loads, so compare its preferred height.
    assert panel.component_all_button.sizeHint().height() == height

    toggle = panel._section_toggles["Advanced"]
    toggle.setChecked(True)
    content = toggle.parentWidget().findChild(QtWidgets.QGroupBox, "sectionContent")
    assert content.geometry().top() == toggle.geometry().bottom() + 1


def test_combo_popups_use_styleable_list_views(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path)
    for combo in (
        panel.input_unit,
        panel.output_unit,
        panel.attitude_mode,
        panel.step_component_mode,
        panel.step_metrics,
        panel.axis_x,
    ):
        assert isinstance(combo.view(), QtWidgets.QListView)


def test_component_list_height_fits_short_lists(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path, "model.step")
    panel.resize(440, 900)
    panel.show()
    qtbot.waitExposed(panel)
    panel.set_model(_model(tmp_path / "model.step", ("A", "B")))
    short = panel.component_scroll.height()
    qtbot.wait(10)  # Let Qt show the new rows before measuring the content.
    content = panel.component_scroll.widget().sizeHint().height()
    assert content + 2 * panel.component_scroll.frameWidth() <= short < 200
    assert not panel.component_scroll.verticalScrollBar().isVisible()

    names = tuple(f"Part {index}" for index in range(30))
    panel.set_model(_model(tmp_path / "model.step", names))
    assert panel.component_scroll.height() == 200


def test_all_and_none_report_one_component_change(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path, "model.step")
    names = tuple(f"Part {index}" for index in range(50))
    panel.set_model(_model(tmp_path / "model.step", names))
    requests = []
    panel.request_changed.connect(requests.append)

    panel.component_none_button.setEnabled(True)
    panel.component_none_button.click()
    assert len(requests) == 1
    assert panel.component_summary.text() == "0 of 50 components enabled."
    assert panel.run_button.isEnabled() is False
    assert "component" in panel.validation_label.text().lower()
    assert panel.components_pending is True
    assert panel._advanced_dirty is False

    panel.component_all_button.click()
    assert len(requests) == 2
    assert requests[-1] is not None
    assert requests[-1].step_components == tuple(range(1, 51))
    assert panel.run_button.isEnabled() is True

    # Nothing changes, so nothing is reported.
    panel.component_all_button.click()
    assert len(requests) == 2


def test_component_selection_is_reported_for_the_viewer(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path, "model.step")
    selections = []
    panel.component_selection_changed.connect(selections.append)
    panel.set_model(_model(tmp_path / "model.step", ("A", "B", "C")))
    assert selections[-1] == ((1, 2, 3), "filter")

    panel._component_checkboxes[1].setChecked(False)
    assert selections[-1] == ((1, 3), "filter")
    panel.step_component_mode.setCurrentIndex(1)
    assert selections[-1] == ((1, 3), "subtract")

    count = len(selections)
    panel.component_none_button.click()
    assert len(selections) == count + 1
    assert selections[-1] == ((), "subtract")

    panel._clear_components()
    assert selections[-1] is None


def test_component_changes_have_their_own_apply_button(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path, "model.step")
    panel.set_model(_model(tmp_path / "model.step", ("A", "B", "C")))
    toggle = panel._section_toggles["Components"]
    assert panel.components_pending is False
    assert panel.component_apply_button.isEnabled() is False
    assert panel.component_status.isHidden() is True

    panel._component_checkboxes[1].setChecked(False)
    assert panel.components_pending is True
    assert panel.component_apply_button.isEnabled() is True
    assert panel.component_apply_button.property("emphasis") is True
    assert panel.component_status.isHidden() is False
    assert "approximate preview" in panel.component_status.text()
    assert toggle.text() == "Components · changes pending"
    # Component edits no longer flag the unrelated Advanced section.
    assert panel._section_toggles["Advanced"].text() == "Advanced"

    panel.step_component_mode.setCurrentIndex(panel.step_component_mode.findData("subtract"))
    assert "not the cut shape" in panel.component_status.text()

    # Restoring the loaded selection and mode clears the pending state.
    panel.step_component_mode.setCurrentIndex(panel.step_component_mode.findData("filter"))
    panel._component_checkboxes[1].setChecked(True)
    assert panel.components_pending is False
    assert panel.component_apply_button.isEnabled() is False
    assert toggle.text() == "Components"


def test_component_apply_button_reloads_the_model(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path, "model.step")
    panel.set_model(_model(tmp_path / "model.step", ("A", "B")))
    reloads = []
    panel.model_reload_requested.connect(reloads.append)
    panel._component_checkboxes[0].setChecked(False)
    panel.component_apply_button.click()
    assert len(reloads) == 1
    assert reloads[0].step_components == (2,)


def test_component_filter_limits_list_and_all_none(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path, "model.step")
    names = tuple(f"Bolt {index}" for index in range(6)) + tuple(f"Panel {i}" for i in range(6))
    panel.set_model(_model(tmp_path / "model.step", names))
    assert panel.component_filter.isHidden() is False

    panel.component_filter.setText("bolt")
    shown = [box for box in panel._component_checkboxes if not box.isHidden()]
    assert len(shown) == 6
    panel.component_none_button.click()
    assert [box.isChecked() for box in panel._component_checkboxes] == [False] * 6 + [True] * 6

    panel.component_filter.clear()
    assert all(not box.isHidden() for box in panel._component_checkboxes)


def test_short_component_lists_have_no_filter(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path, "model.step")
    panel.set_model(_model(tmp_path / "model.step", ("A", "B", "C")))
    assert panel.component_filter.isHidden() is True


def test_toggle_component_and_hover_report(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path, "model.step")
    panel.set_model(_model(tmp_path / "model.step", ("A", "B")))
    hovered = []
    panel.component_hovered.connect(hovered.append)

    assert panel.toggle_component(2) is True
    assert panel._component_checkboxes[1].isChecked() is False
    assert panel._section_toggles["Components"].isChecked() is True
    assert panel.toggle_component(99) is False

    box = panel._component_checkboxes[0]
    QtWidgets.QApplication.sendEvent(box, QtCore.QEvent(QtCore.QEvent.Type.Enter))
    QtWidgets.QApplication.sendEvent(box, QtCore.QEvent(QtCore.QEvent.Type.Leave))
    assert hovered == [1, None]

    panel.set_busy(OperationState.LOADING)
    assert panel.toggle_component(1) is False


def test_file_field_shows_name_until_edited(qtbot, tmp_path: Path) -> None:
    panel = _panel(qtbot, tmp_path, "model.stl")
    path = tmp_path / "model.stl"
    assert panel.file_edit.text() == "model.stl"
    assert panel.file_edit.toolTip() == str(path)
    assert panel.file_paths == (path,)
    assert panel.validation_message() is None

    panel.file_edit.focus_changed.emit(True)
    assert panel.file_edit.text() == str(path)
    assert panel.file_paths == (path,)
    panel.file_edit.focus_changed.emit(False)
    assert panel.file_edit.text() == "model.stl"

    # A path typed by the user is left as typed.
    panel.file_edit.setText(str(tmp_path / "other.stl"))
    panel.file_edit.focus_changed.emit(False)
    assert panel.file_edit.text() == str(tmp_path / "other.stl")
