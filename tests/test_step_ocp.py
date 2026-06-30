from pathlib import Path

import pytest

pytest.importorskip("OCP")

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

from cadmetrics.api import measure, project


def test_generated_step_box_measurements(tmp_path: Path) -> None:
    step_path = tmp_path / "box.step"
    shape = BRepPrimAPI_MakeBox(1000.0, 2000.0, 3000.0).Shape()
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    assert writer.Write(str(step_path)) == IFSelect_RetDone

    measured = measure(step_path)
    assert measured.volume == pytest.approx(6.0)
    assert measured.surface_area == pytest.approx(22.0)
    assert measured.is_watertight is True
    assert measured.mesh_deflection == pytest.approx((1.0**2 + 2.0**2 + 3.0**2) ** 0.5 * 1.0e-5)

    projected = project(step_path)
    assert projected.projected_area == pytest.approx(6.0)
    assert projected.input_unit == "mm"
    assert projected.mesh_deflection == measured.mesh_deflection
