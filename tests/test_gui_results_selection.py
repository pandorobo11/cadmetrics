from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

import cadmetrics.gui.results_panel as results_panel
from cadmetrics.types import MeasurementRow


def test_cocoa_selection_changes_repaint_the_row_without_moving_current(qtbot, monkeypatch):
    monkeypatch.setattr(results_panel.sys, "platform", "darwin")
    panel = results_panel.ResultsPanel()
    qtbot.addWidget(panel)
    panel.set_rows(
        [
            MeasurementRow(
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
        ]
    )
    panel.select_last_row()
    current = panel.table.currentIndex()
    selection = panel.table.selectionModel()
    assert len(selection.selectedIndexes()) == 1

    # Qt only invalidates the native cell for selection-only changes. Track the
    # explicit whole-viewport repaint, rather than grab() which forces painting.
    repaints = []
    monkeypatch.setattr(panel.table.viewport(), "update", lambda: repaints.append(True))
    selection.clearSelection()
    assert panel.table.currentIndex() == current
    assert not selection.hasSelection()
    assert repaints == [True]

    repaints.clear()
    panel.table.setCurrentIndex(current)
    assert panel.table.currentIndex() == current
    assert len(selection.selectedIndexes()) == 1
    assert repaints == [True]
