from pathlib import Path

import pytest

pytest.importorskip("OCP")

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeSphere
from OCP.gp import gp_Pnt
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound

from cadmetrics.api import inspect_model, measure, project
from cadmetrics.cli import app
from cadmetrics._ocp import _usable_step_component_name
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
    assert measured.base_area == pytest.approx(6.0)
    assert measured.is_watertight is True
    assert measured.mesh_deflection == pytest.approx((1.0**2 + 2.0**2 + 3.0**2) ** 0.5 * 1.0e-4)

    projected = project(step_path)
    assert projected.projected_area == pytest.approx(6.0)
    assert projected.input_unit == "mm"
    assert projected.mesh_deflection == measured.mesh_deflection


@pytest.mark.parametrize(
    ("writer_unit", "expected_input_unit"),
    [("M", "m"), ("CM", "cm"), ("INCH", "in"), ("FT", "ft")],
)
def test_declared_step_units_are_converted_once(
    tmp_path: Path,
    writer_unit: str,
    expected_input_unit: str,
) -> None:
    step_path = tmp_path / f"box_{expected_input_unit}.step"
    shape = BRepPrimAPI_MakeBox(1000.0, 2000.0, 3000.0).Shape()
    _write_step_with_unit(step_path, shape, writer_unit)

    inspected = inspect_model(step_path, output_unit="m")
    projected = project(step_path, output_unit="m")

    assert inspected.input_unit == expected_input_unit
    assert inspected.bounds == pytest.approx((0.0, 1.0, 0.0, 2.0, 0.0, 3.0))
    assert inspected.volume == pytest.approx(6.0)
    assert inspected.surface_area == pytest.approx(22.0)
    assert inspected.base_area == pytest.approx(6.0)
    assert inspected.vertices.min(axis=0) == pytest.approx((0.0, 0.0, 0.0))
    assert inspected.vertices.max(axis=0) == pytest.approx((1.0, 2.0, 3.0))
    assert inspected.mesh_deflection == pytest.approx((1.0**2 + 2.0**2 + 3.0**2) ** 0.5 * 1.0e-4)
    assert projected.projected_area == pytest.approx(6.0)


def test_metre_step_keeps_kernel_tolerances_for_sub_micrometre_box(
    tmp_path: Path,
) -> None:
    step_path = tmp_path / "sub_micrometre_box.step"
    side_mm = 1.0e-4
    shape = BRepPrimAPI_MakeBox(side_mm, side_mm, side_mm).Shape()
    _write_step_with_unit(step_path, shape, "M")

    inspected = inspect_model(step_path, output_unit="m")
    explicitly_metre = inspect_model(step_path, input_unit="m", output_unit="m")

    assert inspected.input_unit == "m"
    assert inspected.bounds == pytest.approx(
        (0.0, 1.0e-7, 0.0, 1.0e-7, 0.0, 1.0e-7),
        rel=1.0e-9,
        abs=1.0e-18,
    )
    assert inspected.volume == pytest.approx(1.0e-21, rel=1.0e-6)
    assert inspected.surface_area == pytest.approx(6.0e-14, rel=1.0e-6)
    assert inspected.is_watertight is True
    assert explicitly_metre.bounds == pytest.approx(inspected.bounds)
    assert explicitly_metre.volume == pytest.approx(inspected.volume)
    assert explicitly_metre.surface_area == pytest.approx(inspected.surface_area)
    assert explicitly_metre.is_watertight is True


def test_explicit_step_unit_reinterprets_file_coordinates(tmp_path: Path) -> None:
    step_path = tmp_path / "one_by_two_by_three_inches.step"
    shape = BRepPrimAPI_MakeBox(25.4, 50.8, 76.2).Shape()
    _write_step_with_unit(step_path, shape, "INCH")

    detected = measure(step_path, output_unit="m")
    overridden = measure(step_path, input_unit="m", output_unit="m")

    assert detected.input_unit == "in"
    assert detected.volume == pytest.approx(6.0 * 0.0254**3)
    assert overridden.input_unit == "m"
    assert overridden.volume == pytest.approx(6.0)
    assert overridden.surface_area == pytest.approx(22.0)
    assert overridden.base_area == pytest.approx(6.0)
    assert overridden.x_max == pytest.approx(1.0)
    assert overridden.y_max == pytest.approx(2.0)
    assert overridden.z_max == pytest.approx(3.0)


def test_extended_step_unit_can_be_reinterpreted_explicitly(tmp_path: Path) -> None:
    step_path = tmp_path / "micrometre_box.step"
    shape = BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape()
    _write_step_with_unit(step_path, shape, "UM")

    detected = measure(step_path, output_unit="m")
    overridden = measure(step_path, input_unit="mm", output_unit="m")

    assert detected.input_unit == "mm"
    assert detected.volume == pytest.approx(1.0e-9)
    assert detected.x_max == pytest.approx(0.001)
    assert "converted it to mm" in "; ".join(detected.warnings)
    assert overridden.input_unit == "mm"
    assert overridden.volume == pytest.approx(1.0)
    assert overridden.x_max == pytest.approx(1.0)


def test_non_mm_step_assembly_uses_one_coordinate_unit(tmp_path: Path) -> None:
    step_a = tmp_path / "inch_box_a.step"
    step_b = tmp_path / "inch_box_b.step"
    box_a = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    box_b = BRepPrimAPI_MakeBox(gp_Pnt(500.0, 0.0, 0.0), 1000.0, 1000.0, 1000.0).Shape()
    _write_step_with_unit(step_a, box_a, "INCH")
    _write_step_with_unit(step_b, box_b, "INCH")

    inspected = inspect_model([step_a, step_b], output_unit="m")
    projected = project([step_a, step_b], output_unit="m")

    assert inspected.input_unit == "in"
    assert inspected.bounds == pytest.approx((0.0, 1.5, 0.0, 1.0, 0.0, 1.0))
    assert inspected.volume == pytest.approx(1.5)
    assert inspected.surface_area == pytest.approx(8.0)
    assert inspected.base_area == pytest.approx(1.0)
    assert inspected.vertices.max(axis=0) == pytest.approx((1.5, 1.0, 1.0))
    assert projected.projected_area == pytest.approx(1.0)


def test_explicit_unit_reinterprets_mixed_declarations_in_step_assembly(
    tmp_path: Path,
) -> None:
    millimetre_path = tmp_path / "numeric_mm.step"
    inch_path = tmp_path / "numeric_inch.step"
    _write_step_with_unit(
        millimetre_path,
        BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape(),
        "MM",
    )
    _write_step_with_unit(
        inch_path,
        BRepPrimAPI_MakeBox(gp_Pnt(50.8, 0.0, 0.0), 25.4, 25.4, 25.4).Shape(),
        "INCH",
    )

    with pytest.raises(ValueError, match="different detected units"):
        measure([millimetre_path, inch_path])

    overridden = measure(
        [millimetre_path, inch_path],
        input_unit="m",
        output_unit="m",
    )

    assert overridden.input_unit == "m"
    assert overridden.volume == pytest.approx(2.0)
    assert overridden.surface_area == pytest.approx(12.0)
    assert overridden.base_area == pytest.approx(1.0)
    assert overridden.x_min == pytest.approx(0.0)
    assert overridden.x_max == pytest.approx(3.0)


def test_auto_mesh_deflection_uses_actual_sub_unit_diagonal(tmp_path: Path) -> None:
    step_path = tmp_path / "tiny_sphere.step"
    radius_mm = 0.01
    shape = BRepPrimAPI_MakeSphere(radius_mm).Shape()
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    assert writer.Write(str(step_path)) == IFSelect_RetDone

    inspected = inspect_model(step_path, output_unit="mm")
    projected = project(
        step_path,
        output_unit="mm",
        attitude="vector",
        direction="1,0,0",
    )

    expected_diagonal = 2.0 * radius_mm * 3.0**0.5
    assert inspected.mesh_deflection == pytest.approx(expected_diagonal * 1.0e-4)
    assert projected.projected_area == pytest.approx(
        3.141592653589793 * radius_mm**2,
        rel=1.0e-3,
    )


def test_step_measure_brep_does_not_require_tessellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step_path = tmp_path / "box.step"
    shape = BRepPrimAPI_MakeBox(1000.0, 2000.0, 3000.0).Shape()
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    assert writer.Write(str(step_path)) == IFSelect_RetDone

    def fail_tessellation(*args, **kwargs):
        raise AssertionError("STEP measure should not tessellate in B-Rep metric mode")

    monkeypatch.setattr("cadmetrics._ocp._tessellate_ocp_shape", fail_tessellation)

    measured = measure(step_path)

    assert measured.volume == pytest.approx(6.0)
    assert measured.surface_area == pytest.approx(22.0)
    assert measured.base_area == pytest.approx(6.0)
    assert measured.x_max == pytest.approx(1.0)
    assert measured.y_max == pytest.approx(2.0)
    assert measured.z_max == pytest.approx(3.0)


def test_step_inspect_can_skip_mesh_but_keep_bounds(tmp_path: Path) -> None:
    step_path = tmp_path / "box.step"
    shape = BRepPrimAPI_MakeBox(1000.0, 2000.0, 3000.0).Shape()
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    assert writer.Write(str(step_path)) == IFSelect_RetDone

    inspected = inspect_model(step_path, require_mesh=False)

    assert inspected.vertex_count == 0
    assert inspected.face_count == 0
    assert inspected.x_min == pytest.approx(0.0)
    assert inspected.x_max == pytest.approx(1.0)
    assert inspected.y_min == pytest.approx(0.0)
    assert inspected.y_max == pytest.approx(2.0)
    assert inspected.z_min == pytest.approx(0.0)
    assert inspected.z_max == pytest.approx(3.0)
    assert inspected.volume == pytest.approx(6.0)
    assert inspected.surface_area == pytest.approx(22.0)


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


@pytest.mark.parametrize("metric_source", ["brep", "mesh"])
def test_open_step_shape_leaves_volume_unset(tmp_path: Path, metric_source: str) -> None:
    step_path = tmp_path / "open_box.step"
    _write_open_step_box(step_path)

    measured = measure(step_path, step_metric_source=metric_source)

    assert measured.volume is None
    assert measured.surface_area == pytest.approx(5.0)
    assert measured.is_watertight is False
    assert "volume was left unset" in "; ".join(measured.warnings)


def test_step_shape_with_loose_face_is_not_watertight(tmp_path: Path) -> None:
    step_path = tmp_path / "solid_with_loose_face.step"
    solid = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    extra_shape = BRepPrimAPI_MakeBox(
        gp_Pnt(2000.0, 0.0, 0.0), 1000.0, 1000.0, 1000.0
    ).Shape()
    explorer = TopExp_Explorer(extra_shape, TopAbs_FACE)
    extra_face = TopoDS.Face_s(explorer.Current())
    _write_step_compound(step_path, [solid, extra_face])

    measured = measure(step_path)

    assert measured.volume is None
    assert measured.is_watertight is False
    assert "non-solid faces" in "; ".join(measured.warnings)


def test_step_shape_with_multiple_solids_preserves_loose_face(tmp_path: Path) -> None:
    step_path = tmp_path / "multiple_solids_with_loose_face.step"
    first = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    second = BRepPrimAPI_MakeBox(
        gp_Pnt(3000.0, 0.0, 0.0), 1000.0, 1000.0, 1000.0
    ).Shape()
    polygon = BRepBuilderAPI_MakePolygon()
    polygon.Add(gp_Pnt(5000.0, 2000.0, 0.0))
    polygon.Add(gp_Pnt(5000.0, 3000.0, 0.0))
    polygon.Add(gp_Pnt(5000.0, 3000.0, 1000.0))
    polygon.Add(gp_Pnt(5000.0, 2000.0, 1000.0))
    polygon.Close()
    loose_face = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    _write_step_compound(step_path, [first, second, loose_face])

    measured = measure(step_path)
    projected = project(step_path)

    assert measured.volume is None
    assert measured.surface_area == pytest.approx(13.0)
    assert measured.is_watertight is False
    assert measured.x_max == pytest.approx(5.0)
    assert measured.y_max == pytest.approx(3.0)
    assert "non-solid faces" in "; ".join(measured.warnings)
    assert projected.surface_area == pytest.approx(13.0)
    assert projected.projected_area == pytest.approx(2.0)


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


@pytest.mark.parametrize("metric_source", ["brep", "mesh"])
def test_step_subtract_mode_removes_disabled_overlap_and_excludes_cut_face(
    tmp_path: Path,
    metric_source: str,
) -> None:
    step_path = tmp_path / "subtracting_boxes.step"
    enabled = BRepPrimAPI_MakeBox(2000.0, 1000.0, 1000.0).Shape()
    disabled = BRepPrimAPI_MakeBox(
        gp_Pnt(1000.0, 0.0, 0.0), 1000.0, 1000.0, 1000.0
    ).Shape()
    _write_step_compound(step_path, [enabled, disabled])

    filtered = measure(step_path, step_components=(1,), step_metric_source=metric_source)
    subtracted = measure(
        step_path,
        step_components=(1,),
        step_component_mode="subtract",
        step_metric_source=metric_source,
    )
    inspected = inspect_model(
        step_path,
        step_components=(1,),
        step_component_mode="subtract",
        step_metric_source=metric_source,
    )
    reversed_axis = measure(
        step_path,
        step_components=(1,),
        step_component_mode="subtract",
        step_metric_source=metric_source,
        axis_map="-x,y,z",
    )

    assert filtered.volume == pytest.approx(2.0)
    assert filtered.surface_area == pytest.approx(10.0)
    assert filtered.newly_exposed_surface_area is None
    assert subtracted.volume == pytest.approx(1.0)
    assert subtracted.surface_area == pytest.approx(5.0)
    assert subtracted.newly_exposed_surface_area == pytest.approx(1.0)
    assert subtracted.base_area == pytest.approx(0.0)
    assert subtracted.step_component_mode == "subtract"
    assert "subtract" in (subtracted.method or "")
    assert len(inspected.newly_exposed_face_indices) == 2
    assert reversed_axis.base_area == pytest.approx(1.0)


def test_step_subtract_mode_excludes_internal_cavity_surface(tmp_path: Path) -> None:
    step_path = tmp_path / "internal_cavity.step"
    enabled = BRepPrimAPI_MakeBox(3000.0, 3000.0, 3000.0).Shape()
    disabled = BRepPrimAPI_MakeBox(
        gp_Pnt(1000.0, 1000.0, 1000.0), 1000.0, 1000.0, 1000.0
    ).Shape()
    _write_step_compound(step_path, [enabled, disabled])

    measured = measure(
        step_path,
        step_components=(1,),
        step_component_mode="subtract",
    )

    assert measured.volume == pytest.approx(26.0)
    assert measured.surface_area == pytest.approx(54.0)
    assert measured.newly_exposed_surface_area == pytest.approx(6.0)
    assert measured.base_area == pytest.approx(9.0)


def test_step_subtract_mode_returns_zero_for_empty_result(tmp_path: Path) -> None:
    step_path = tmp_path / "empty_subtraction.step"
    enabled = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    disabled = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    _write_step_compound(step_path, [enabled, disabled])

    measured = measure(
        step_path,
        step_components=(1,),
        step_component_mode="subtract",
    )
    projected = project(
        step_path,
        step_components=(1,),
        step_component_mode="subtract",
    )

    assert measured.volume == pytest.approx(0.0)
    assert measured.surface_area == pytest.approx(0.0)
    assert measured.newly_exposed_surface_area == pytest.approx(0.0)
    assert measured.x_min is None
    assert projected.projected_area == pytest.approx(0.0)
    assert "empty shape" in "; ".join(measured.warnings)


def test_step_subtract_mode_with_all_components_selected_is_a_noop(tmp_path: Path) -> None:
    step_path = tmp_path / "all_selected.step"
    enabled = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    other = BRepPrimAPI_MakeBox(
        gp_Pnt(500.0, 0.0, 0.0), 1000.0, 1000.0, 1000.0
    ).Shape()
    _write_step_compound(step_path, [enabled, other])

    measured = measure(step_path, step_component_mode="subtract")

    assert measured.volume == pytest.approx(1.5)
    assert measured.surface_area == pytest.approx(8.0)
    assert measured.newly_exposed_surface_area is None


@pytest.mark.parametrize("disabled_x", [1000.0, 2000.0])
def test_step_subtract_mode_preserves_nonoverlapping_enabled_shape(
    tmp_path: Path,
    disabled_x: float,
) -> None:
    step_path = tmp_path / f"nonoverlapping_subtraction_{disabled_x:g}.step"
    enabled = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    disabled = BRepPrimAPI_MakeBox(
        gp_Pnt(disabled_x, 0.0, 0.0), 1000.0, 1000.0, 1000.0
    ).Shape()
    _write_step_compound(step_path, [enabled, disabled])

    measured = measure(
        step_path,
        step_components=(1,),
        step_component_mode="subtract",
    )

    assert measured.volume == pytest.approx(1.0)
    assert measured.surface_area == pytest.approx(6.0)
    assert measured.newly_exposed_surface_area == pytest.approx(0.0)


def test_step_subtract_mode_cli_options_and_inspect_component_list(tmp_path: Path) -> None:
    step_path = tmp_path / "cli_subtract.step"
    enabled = BRepPrimAPI_MakeBox(2000.0, 1000.0, 1000.0).Shape()
    disabled = BRepPrimAPI_MakeBox(
        gp_Pnt(1000.0, 0.0, 0.0), 1000.0, 1000.0, 1000.0
    ).Shape()
    _write_step_compound(step_path, [enabled, disabled])

    measured = CliRunner().invoke(
        app,
        [
            "measure",
            str(step_path),
            "--step-component",
            "1",
            "--component-mode",
            "subtract",
        ],
    )
    inspected = CliRunner().invoke(app, ["inspect", str(step_path)])

    assert measured.exit_code == 0, measured.output
    assert "newly_exposed_surface_area" in measured.output
    assert "step-brep-subtract" in measured.output
    assert inspected.exit_code == 0, inspected.output
    assert "component_list" in inspected.output
    assert "1: Component 1" in inspected.output


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

    subtracted = measure(
        [step_a, step_b],
        step_components=(1,),
        step_component_mode="subtract",
    )
    assert subtracted.volume == pytest.approx(0.5)
    assert subtracted.surface_area == pytest.approx(3.0)
    assert subtracted.newly_exposed_surface_area == pytest.approx(1.0)
    assert subtracted.base_area == pytest.approx(0.0)
    assert subtracted.method == "step-brep-subtract-assembly"


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
    assert measured.base_area == pytest.approx(2.0)
    assert measured.method == "step-brep-assembly"
    assert measured.step_components == (2, 3)
    assert measured.step_component_names == (
        "body.step: Component 2",
        "wing.step: Component 1",
    )

    projected = project([step_a, step_b], step_components=(2, 3))
    assert projected.projected_area == pytest.approx(2.0)
    assert projected.method == "step-brep-assembly+mesh-projection"
    assert projected.step_components == (2, 3)
    assert projected.step_component_names == (
        "body.step: Component 2",
        "wing.step: Component 1",
    )


def test_step_assembly_preserves_surface_only_file_alongside_solid(tmp_path: Path) -> None:
    solid_path = tmp_path / "solid.step"
    surface_path = tmp_path / "surface.step"
    _write_step_compound(
        solid_path,
        [BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()],
    )

    polygon = BRepBuilderAPI_MakePolygon()
    polygon.Add(gp_Pnt(2000.0, 2000.0, 0.0))
    polygon.Add(gp_Pnt(2000.0, 3000.0, 0.0))
    polygon.Add(gp_Pnt(2000.0, 3000.0, 1000.0))
    polygon.Add(gp_Pnt(2000.0, 2000.0, 1000.0))
    polygon.Close()
    surface = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    _write_step_compound(surface_path, [surface])

    measured = measure([solid_path, surface_path])
    projected = project([solid_path, surface_path])

    assert measured.volume is None
    assert measured.surface_area == pytest.approx(7.0)
    assert measured.is_watertight is False
    assert measured.x_max == pytest.approx(2.0)
    assert measured.y_max == pytest.approx(3.0)
    assert "non-solid faces" in "; ".join(measured.warnings)
    assert projected.surface_area == pytest.approx(7.0)
    assert projected.projected_area == pytest.approx(2.0)
    assert projected.is_watertight is False


def test_step_assembly_preserves_loose_face_from_file_that_also_has_solid(
    tmp_path: Path,
) -> None:
    hybrid_path = tmp_path / "hybrid.step"
    other_solid_path = tmp_path / "other_solid.step"
    solid = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    polygon = BRepBuilderAPI_MakePolygon()
    polygon.Add(gp_Pnt(2000.0, 2000.0, 0.0))
    polygon.Add(gp_Pnt(2000.0, 3000.0, 0.0))
    polygon.Add(gp_Pnt(2000.0, 3000.0, 1000.0))
    polygon.Add(gp_Pnt(2000.0, 2000.0, 1000.0))
    polygon.Close()
    loose_face = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    _write_step_compound(hybrid_path, [solid, loose_face])
    _write_step_compound(
        other_solid_path,
        [
            BRepPrimAPI_MakeBox(
                gp_Pnt(4000.0, 0.0, 0.0), 1000.0, 1000.0, 1000.0
            ).Shape()
        ],
    )

    measured = measure([hybrid_path, other_solid_path])
    projected = project([hybrid_path, other_solid_path])

    assert measured.volume is None
    assert measured.surface_area == pytest.approx(13.0)
    assert measured.is_watertight is False
    assert (
        measured.x_min,
        measured.x_max,
        measured.y_min,
        measured.y_max,
        measured.z_min,
        measured.z_max,
    ) == pytest.approx((0.0, 5.0, 0.0, 3.0, 0.0, 1.0))
    assert "non-solid faces" in "; ".join(measured.warnings)
    assert projected.surface_area == pytest.approx(13.0)
    assert projected.projected_area == pytest.approx(2.0)


def test_step_base_area_uses_axis_mapped_xmax(tmp_path: Path) -> None:
    step_path = tmp_path / "asymmetric_ends.step"
    small_end = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    large_end = BRepPrimAPI_MakeBox(
        gp_Pnt(1000.0, 0.0, 0.0),
        1000.0,
        2000.0,
        1000.0,
    ).Shape()
    _write_step_compound(step_path, [small_end, large_end])

    positive_x = measure(step_path)
    negative_x = measure(step_path, axis_map="-x,y,z")

    assert positive_x.base_area == pytest.approx(2.0)
    assert negative_x.base_area == pytest.approx(1.0)


def test_step_base_area_falls_back_to_mesh_when_exact_calculation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step_path = tmp_path / "box.step"
    shape = BRepPrimAPI_MakeBox(1000.0, 2000.0, 3000.0).Shape()
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    assert writer.Write(str(step_path)) == IFSelect_RetDone

    monkeypatch.setattr(
        "cadmetrics._step_io._ocp_xmax_base_area",
        lambda *args, **kwargs: (0.0, False, True),
    )

    measured = measure(step_path)

    assert measured.base_area == pytest.approx(6.0)
    assert "mesh fallback" in "; ".join(measured.warnings)


def test_step_subtract_base_area_mesh_fallback_excludes_newly_exposed_faces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step_path = tmp_path / "subtract_base_fallback.step"
    enabled = BRepPrimAPI_MakeBox(2000.0, 1000.0, 1000.0).Shape()
    disabled = BRepPrimAPI_MakeBox(
        gp_Pnt(1000.0, 0.0, 0.0), 1000.0, 1000.0, 1000.0
    ).Shape()
    _write_step_compound(step_path, [enabled, disabled])
    monkeypatch.setattr(
        "cadmetrics._step_io._ocp_xmax_base_area",
        lambda *args, **kwargs: (0.0, False, True),
    )

    measured = measure(
        step_path,
        step_components=(1,),
        step_component_mode="subtract",
    )

    assert measured.base_area == pytest.approx(0.0)
    assert "excluding newly exposed surfaces" in "; ".join(measured.warnings)


def test_step_subtract_base_area_is_unset_when_face_classification_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step_path = tmp_path / "subtract_unclassified_faces.step"
    enabled = BRepPrimAPI_MakeBox(2000.0, 1000.0, 1000.0).Shape()
    disabled = BRepPrimAPI_MakeBox(
        gp_Pnt(1000.0, 0.0, 0.0), 1000.0, 1000.0, 1000.0
    ).Shape()
    _write_step_compound(step_path, [enabled, disabled])
    monkeypatch.setattr(
        "cadmetrics._ocp._classify_cut_result_faces",
        lambda *args, **kwargs: (None, None),
    )

    measured = measure(
        step_path,
        step_components=(1,),
        step_component_mode="subtract",
    )

    assert measured.base_area is None
    assert "base_area was left unset" in "; ".join(measured.warnings)


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


def _write_step_with_unit(path: Path, shape, writer_unit: str) -> None:
    # Construct once so OpenCascade registers the Interface_Static parameters.
    STEPControl_Writer()
    previous_unit = Interface_Static.CVal_s("write.step.unit")
    assert Interface_Static.SetCVal_s("write.step.unit", writer_unit)
    try:
        writer = STEPControl_Writer()
        writer.Transfer(shape, STEPControl_AsIs)
        assert writer.Write(str(path)) == IFSelect_RetDone
    finally:
        assert Interface_Static.SetCVal_s("write.step.unit", previous_unit)


def _write_open_step_box(path: Path) -> None:
    shape = BRepPrimAPI_MakeBox(1000.0, 1000.0, 1000.0).Shape()
    faces = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        faces.append(TopoDS.Face_s(explorer.Current()))
        explorer.Next()
    _write_step_compound(path, faces[:-1])
