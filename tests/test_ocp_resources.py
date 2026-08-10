from pathlib import Path

import pytest

pytest.importorskip("OCP")

from OCP.XCAFApp import XCAFApp_Application

from cadmetrics._ocp import _step_component_names_from_xcaf


SAMPLE_STEP = Path(__file__).parents[1] / "samples" / "unit_cube" / "unit_cube.step"


@pytest.mark.parametrize(
    ("path", "expected_count", "returned_count"),
    [
        (SAMPLE_STEP, 1, 1),
        (SAMPLE_STEP, 2, 0),
        (SAMPLE_STEP.with_name("missing.step"), 1, 0),
    ],
)
def test_xcaf_component_name_reader_does_not_register_document(
    path: Path,
    expected_count: int,
    returned_count: int,
) -> None:
    app = XCAFApp_Application.GetApplication_s()
    document_count = app.NbDocuments()

    names = _step_component_names_from_xcaf(path, expected_count=expected_count)

    assert len(names) == returned_count
    assert app.NbDocuments() == document_count
