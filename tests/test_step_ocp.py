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
    assert "method" in result.output
    assert "step-mesh" in result.output


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


def test_step_assembly_files_are_boolean_unioned_for_measurements(tmp_path: Path) -> None:
    step_a = tmp_path / "box_a.step"
    step_b = tmp_path / "box_b.step"
    box_a = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    box_b = BRepPrimAPI_MakeBox(gp_Pnt(500.0, 0.0, 0.0), 1000.0, 1000.0, 1000.0).Shape()

    writer_a = STEPControl_Writer()
    writer_a.Transfer(box_a, STEPControl_AsIs)
    assert writer_a.Write(str(step_a)) == IFSelect_RetDone
    writer_b = STEPControl_Writer()
    writer_b.Transfer(box_b, STEPControl_AsIs)
    assert writer_b.Write(str(step_b)) == IFSelect_RetDone

    measured = measure([step_a, step_b])
    assert measured.volume == pytest.approx(1.5)
    assert measured.surface_area == pytest.approx(8.0)
    assert measured.is_watertight is True
    assert measured.method == "step-brep-assembly"

    projected = project([step_a, step_b])
    assert projected.projected_area == pytest.approx(1.0)
    assert projected.method == "step-brep-assembly+mesh-projection"


def test_step_assembly_files_accept_global_component_selection(tmp_path: Path) -> None:
    step_a = tmp_path / "body.step"
    step_b = tmp_path / "wing.step"
    box_a1 = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    box_a2 = BRepPrimAPI_MakeBox(gp_Pnt(0.0, 2000.0, 0.0), 1000.0, 1000.0, 1000.0).Shape()
    box_b1 = BRepPrimAPI_MakeBox(gp_Pnt(0.0, 4000.0, 0.0), 1000.0, 1000.0, 1000.0).Shape()

    _write_step_compound(step_a, [box_a1, box_a2])
    _write_step_compound(step_b, [box_b1])

    inspected = inspect_model([step_a, step_b])
    assert inspected.component_names == (
        "body.step: Component 1",
        "body.step: Component 2",
        "wing.step: Component 1",
    )
    assert inspected.selected_components == (1, 2, 3)

    measured = measure([step_a, step_b], step_components=(2, 3))
    assert measured.volume == pytest.approx(2.0)
    assert measured.surface_area == pytest.approx(12.0)
    assert measured.method == "step-brep-assembly"

    projected = project([step_a, step_b], step_components=(2, 3))
    assert projected.projected_area == pytest.approx(2.0)
    assert projected.method == "step-brep-assembly+mesh-projection"


def test_step_assembly_component_selection_can_exclude_an_entire_file(tmp_path: Path) -> None:
    step_a = tmp_path / "body.step"
    step_b = tmp_path / "wing.step"
    _write_step_compound(step_a, [BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()])
    _write_step_compound(
        step_b,
        [BRepPrimAPI_MakeBox(gp_Pnt(0.0, 2000.0, 0.0), 1000.0, 1000.0, 1000.0).Shape()],
    )

    measured = measure([step_a, step_b], step_components=(2,))

    assert measured.volume == pytest.approx(1.0)
    assert measured.surface_area == pytest.approx(6.0)
    assert measured.is_watertight is True


def test_step_assembly_component_selection_rejects_empty_and_out_of_range(tmp_path: Path) -> None:
    step_a = tmp_path / "body.step"
    step_b = tmp_path / "wing.step"
    _write_step_compound(step_a, [BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()])
    _write_step_compound(step_b, [BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()])

    with pytest.raises(ValueError, match="Select at least one STEP component"):
        measure([step_a, step_b], step_components=())
    with pytest.raises(ValueError, match="STEP component index out of range"):
        measure([step_a, step_b], step_components=(3,))


def test_mixed_step_and_stl_assembly_is_rejected(tmp_path: Path) -> None:
    step_path = tmp_path / "box.step"
    shape = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    assert writer.Write(str(step_path)) == IFSelect_RetDone

    with pytest.raises(ValueError, match="mixed STEP and STL"):
        measure([step_path, Path("tests/data/unit_cube.stl")])


def test_step_component_name_filter_rejects_internal_names() -> None:
    assert _usable_step_component_name("wing") == "wing"
    assert _usable_step_component_name("  horizontal tail:1  ") == "horizontal tail:1"
    assert _usable_step_component_name("3") is None
    assert _usable_step_component_name("Open CASCADE STEP translator 7.9 6") is None


def _write_step_compound(path: Path, shapes) -> None:
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)
    assert writer.Write(str(path)) == IFSelect_RetDone
