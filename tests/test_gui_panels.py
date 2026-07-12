from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")

from cadmetrics.gui.control_panel import ControlPanel
from cadmetrics.gui.gui_types import OperationState
from cadmetrics.gui.results_panel import ResultsPanel
from cadmetrics.types import MeasurementRow, ModelData


def test_control_panel_builds_roll_pitch_request(qtbot, tmp_path: Path) -> None:
    path = tmp_path / "model.step"
    path.touch()
    panel = ControlPanel()
    qtbot.addWidget(panel)
    panel.set_file_paths((path,))
    panel.attitude_mode.setCurrentIndex(panel.attitude_mode.findData("roll_pitch"))
    panel.roll_fields[0].setValue(5.0)
    panel.roll_fields[1].setValue(10.0)
    panel.pitch_fields[0].setValue(2.0)

    request = panel.request()

    assert request.file == path
    assert request.attitude_mode == "roll_pitch"
    assert (request.roll_start, request.roll_end) == (5.0, 10.0)
    assert request.pitch_start == 2.0


def test_control_panel_busy_state_enables_only_cancel(qtbot) -> None:
    panel = ControlPanel()
    qtbot.addWidget(panel)

    panel.set_busy(OperationState.LOADING)

    assert panel.run_button.isEnabled() is False
    assert panel.file_edit.isEnabled() is False
    assert panel.cancel_button.isEnabled() is True

    panel.set_busy(OperationState.CANCELLING)
    assert panel.cancel_button.isEnabled() is False


def test_control_panel_populates_step_components(qtbot, tmp_path: Path) -> None:
    path = tmp_path / "assembly.step"
    path.touch()
    panel = ControlPanel()
    qtbot.addWidget(panel)
    panel.set_file_paths((path,))
    panel.set_model(_model(path, component_names=("Body", "Wing")))

    panel._component_checkboxes[1].setChecked(False)
    request = panel.request()

    assert request.step_components == (1,)
    assert panel.component_summary.text() == "1 of 2 components enabled."


def test_results_panel_displays_selects_and_exports_rows(qtbot, tmp_path: Path) -> None:
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    row = _row()
    selected = []
    panel.selected_row_changed.connect(selected.append)

    panel.set_rows([row])
    panel.select_last_row()
    output = tmp_path / "rows.csv"
    panel.save_csv(output)

    assert panel.result_count.text() == "Rows: 1"
    assert selected == [row]
    assert output.read_text(encoding="utf-8").startswith("file,step_components")


def _model(path: Path, *, component_names: tuple[str, ...]) -> ModelData:
    return ModelData(
        path=path,
        source_format="step",
        vertices=np.empty((0, 3), dtype=float),
        faces=np.empty((0, 3), dtype=np.int64),
        input_unit="m",
        output_unit="m",
        volume=1.0,
        surface_area=6.0,
        base_area=1.0,
        is_watertight=True,
        component_names=component_names,
        selected_components=tuple(range(1, len(component_names) + 1)),
    )


def _row() -> MeasurementRow:
    return MeasurementRow(
        file="model.stl",
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
