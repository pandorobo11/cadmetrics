import csv
from pathlib import Path

import pytest

pytest.importorskip("OCP")

from OCP.BRep import BRep_Builder
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Pnt
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopoDS import TopoDS_Compound

from cadmetrics.api import inspect_model, measure, project
from cadmetrics.cli import app
from cadmetrics.io import _usable_step_component_name
from typer.testing import CliRunner


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
    assert measured.mesh_deflection == pytest.approx((1.0**2 + 2.0**2 + 3.0**2) ** 0.5 * 1.0e-4)

    projected = project(step_path)
    assert projected.projected_area == pytest.approx(6.0)
    assert projected.input_unit == "mm"
    assert projected.mesh_deflection == measured.mesh_deflection


def test_step_box_can_use_tessellated_mesh_metrics(tmp_path: Path) -> None:
    step_path = tmp_path / "box.step"
    shape = BRepPrimAPI_MakeBox(1000.0, 2000.0, 3000.0).Shape()
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    assert writer.Write(str(step_path)) == IFSelect_RetDone

    measured = measure(step_path, step_metric_source="mesh")
    assert measured.volume == pytest.approx(6.0)
    assert measured.surface_area == pytest.approx(22.0)
    assert measured.is_watertight is True
    assert measured.method == "step-mesh"
    assert "tessellated mesh" in "; ".join(measured.warnings)

    projected = project(step_path, step_metric_source="mesh")
    assert projected.method == "step-mesh+mesh-projection"
    assert projected.volume == pytest.approx(measured.volume)
    assert projected.surface_area == pytest.approx(measured.surface_area)


def test_step_metrics_mesh_cli_option(tmp_path: Path) -> None:
    step_path = tmp_path / "box.step"
    shape = BRepPrimAPI_MakeBox(1000.0, 2000.0, 3000.0).Shape()
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    assert writer.Write(str(step_path)) == IFSelect_RetDone

    result = CliRunner().invoke(app, ["measure", str(step_path), "--step-metrics", "mesh"])

    assert result.exit_code == 0, result.output
    rows = list(csv.DictReader(result.output.splitlines()))
    assert rows[0]["method"] == "step-mesh"


def test_step_overlapping_solids_are_boolean_unioned_for_measurements(tmp_path: Path) -> None:
    step_path = tmp_path / "overlapping_boxes.step"
    box_a = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    box_b = BRepPrimAPI_MakeBox(gp_Pnt(500.0, 0.0, 0.0), 1000.0, 1000.0, 1000.0).Shape()

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    builder.Add(compound, box_a)
    builder.Add(compound, box_b)

    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)
    assert writer.Write(str(step_path)) == IFSelect_RetDone

    measured = measure(step_path)
    assert measured.volume == pytest.approx(1.5)
    assert measured.surface_area == pytest.approx(8.0)
    assert measured.is_watertight is True

    component_1 = measure(step_path, step_components=(1,))
    assert component_1.volume == pytest.approx(1.0)
    assert component_1.surface_area == pytest.approx(6.0)

    inspected = inspect_model(step_path, step_components=(2,))
    assert inspected.component_names == ("Component 1", "Component 2")
    assert inspected.selected_components == (2,)
    assert inspected.volume == pytest.approx(1.0)
    assert inspected.surface_area == pytest.approx(6.0)


def test_step_component_name_filter_rejects_internal_names() -> None:
    assert _usable_step_component_name("wing") == "wing"
    assert _usable_step_component_name("  horizontal tail:1  ") == "horizontal tail:1"
    assert _usable_step_component_name("3") is None
    assert _usable_step_component_name("Open CASCADE STEP translator 7.9 6") is None
