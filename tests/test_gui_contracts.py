from __future__ import annotations

from pathlib import Path

from cadmetrics.gui.gui_formatters import (
    component_display_groups,
    format_file_selection,
    format_model_file_label,
)


def test_gui_file_and_component_formatters() -> None:
    paths = (Path("/tmp/body.step"), Path("/tmp/wing.step"), Path("/tmp/tail.step"))

    assert format_file_selection(paths) == "body.step + 2 more"
    assert format_model_file_label(Path("; ".join(str(path) for path in paths))) == (
        "body.step + wing.step + tail.step"
    )
    assert component_display_groups(
        ("body.step: Body", "body.step: Fairing", "wing.step: Wing"), grouped=True
    ) == [
        ("body.step", [(1, "Body"), (2, "Fairing")]),
        ("wing.step", [(3, "Wing")]),
    ]
