from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

from cadmetrics._mesh_io import (
    _assembly_path,
    _empty_mesh,
    _mesh_volume_and_surface_area,
    _mesh_xmax_base_area,
)
from cadmetrics._ocp import (
    OcpBindings,
    _build_step_component_shape,
    _extract_ocp_non_solid_faces,
    _extract_ocp_solids,
    _ocp_bounding_box_diagonal,
    _ocp_bounds,
    _ocp_shape_has_subshape,
    _ocp_shape_is_watertight,
    _ocp_shape_metric,
    _ocp_shapes_surface_area,
    _ocp_volume_metric_gk,
    _ocp_xmax_base_area,
    _resolve_step_component_selection,
    _scaled_output_bounds,
    _step_component_names_from_xcaf,
    _step_length_unit_name,
    _step_unit_name_to_length_unit,
    _step_unit_name_to_millimetres,
    _tessellate_ocp_shape_with_marked_faces,
    _tessellated_ocp_shapes_surface_area,
    load_ocp_bindings,
)
from cadmetrics.load_options import normalize_step_metric_source
from cadmetrics.types import FloatArray, IntArray, ModelData
from cadmetrics.units import area_scale, length_scale, normalize_unit, volume_scale


@dataclass(frozen=True)
class PreparedStepInput:
    path: Path
    original_shape: Any
    solids: tuple[Any, ...]
    additional_shapes: tuple[Any, ...]
    component_names: tuple[str, ...]
    resolved_input_unit: str
    kernel_unit: str
    warnings: tuple[str, ...]
    is_assembly: bool


@dataclass(frozen=True)
class ReadStepFile:
    shape: Any
    declared_unit_name: str | None
    resolved_input_unit: str
    kernel_unit: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PreparedStepAssemblyPart:
    path: Path
    shape: Any
    solids: tuple[Any, ...]
    non_solid_shapes: tuple[Any, ...]
    component_names: tuple[str, ...]
    declared_unit: str
    resolved_input_unit: str
    kernel_unit: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class StepFinalizationOptions:
    output_unit: str
    mesh_deflection: float | str
    angular_deflection: float
    metric_source: str
    step_components: tuple[int, ...] | None
    step_component_mode: str
    base_axis_map: str
    base_tolerance: float
    require_mesh: bool


@dataclass(frozen=True)
class SelectedStepShape:
    shape: Any
    selected_components: tuple[int, ...]
    retained_faces: tuple[Any, ...] | None
    cut_faces: tuple[Any, ...] | None
    empty_result: bool
    topology_watertight: bool
    subtraction_active: bool
    face_classification_failed: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class StepGeometry:
    scale: float
    bounds: tuple[float, float, float, float, float, float] | None
    native_diagonal: float
    mesh_deflection: float
    native_mesh_deflection: float


@dataclass(frozen=True)
class ExactStepMetrics:
    volume: float | None
    surface_area: float | None
    newly_exposed_surface_area: float | None
    base_area: float | None
    base_found: bool
    base_failed: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class TessellatedStepShape:
    vertices: FloatArray
    faces: IntArray
    newly_exposed_face_indices: tuple[int, ...]


@dataclass(frozen=True)
class StepBaseMetric:
    area: float | None
    found: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class NativeStepMetrics:
    volume: float | None
    surface_area: float | None
    newly_exposed_surface_area: float | None
    mesh_watertight: bool | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ValidatedStepMetrics:
    volume: float | None
    surface_area: float | None
    newly_exposed_surface_area: float | None
    mesh_watertight: bool | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ScaledStepMetrics:
    volume: float | None
    surface_area: float | None
    newly_exposed_surface_area: float | None
    is_watertight: bool | None
    warnings: tuple[str, ...]


def _load_step(
    path: Path,
    *,
    input_unit: str,
    output_unit: str,
    mesh_deflection: float | str,
    angular_deflection: float,
    step_metric_source: str,
    step_components: tuple[int, ...] | None,
    step_component_mode: str,
    base_axis_map: str,
    base_tolerance: float,
    require_mesh: bool,
) -> ModelData:
    ocp = load_ocp_bindings()
    prepared = _prepare_step_input(path, input_unit=input_unit, ocp=ocp)
    return _finalize_step_model(
        prepared,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
        step_metric_source=step_metric_source,
        step_components=step_components,
        step_component_mode=step_component_mode,
        base_axis_map=base_axis_map,
        base_tolerance=base_tolerance,
        require_mesh=require_mesh,
        ocp=ocp,
    )


def _load_step_assembly(
    paths: tuple[Path, ...],
    *,
    input_unit: str,
    output_unit: str,
    mesh_deflection: float | str,
    angular_deflection: float,
    step_metric_source: str,
    step_components: tuple[int, ...] | None,
    step_component_mode: str,
    base_axis_map: str,
    base_tolerance: float,
    require_mesh: bool,
) -> ModelData:
    ocp = load_ocp_bindings()
    prepared = _prepare_step_assembly_input(
        paths,
        input_unit=input_unit,
        ocp=ocp,
    )
    return _finalize_step_model(
        prepared,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
        step_metric_source=step_metric_source,
        step_components=step_components,
        step_component_mode=step_component_mode,
        base_axis_map=base_axis_map,
        base_tolerance=base_tolerance,
        require_mesh=require_mesh,
        ocp=ocp,
    )


def _prepare_step_input(
    path: Path,
    *,
    input_unit: str,
    ocp: OcpBindings,
) -> PreparedStepInput:
    read_result = _read_step_file(path, input_unit=input_unit, ocp=ocp)
    source_shape = read_result.shape
    solids = tuple(
        _extract_ocp_solids(
            source_shape,
            TopAbs_SOLID=ocp.TopAbs_SOLID,
            TopExp_Explorer=ocp.TopExp_Explorer,
            TopoDS=ocp.TopoDS,
        )
    )
    additional_shapes: tuple[Any, ...] = ()
    original_shape = source_shape
    if solids:
        additional_shapes = tuple(
            _extract_ocp_non_solid_faces(
                source_shape,
                solids,
                TopAbs_FACE=ocp.TopAbs_FACE,
                TopExp_Explorer=ocp.TopExp_Explorer,
            )
        )
        builder = ocp.BRep_Builder()
        solids_shape = ocp.TopoDS_Compound()
        builder.MakeCompound(solids_shape)
        for solid in solids:
            builder.Add(solids_shape, solid)
        original_shape = solids_shape
    component_names = _component_names(path, solids)
    return PreparedStepInput(
        path=path,
        original_shape=original_shape,
        solids=solids,
        additional_shapes=additional_shapes,
        component_names=component_names,
        resolved_input_unit=read_result.resolved_input_unit,
        kernel_unit=read_result.kernel_unit,
        warnings=read_result.warnings,
        is_assembly=False,
    )


def _prepare_step_assembly_input(
    paths: tuple[Path, ...],
    *,
    input_unit: str,
    ocp: OcpBindings,
) -> PreparedStepInput:
    parts = tuple(
        _prepare_step_assembly_part(path, input_unit=input_unit, ocp=ocp) for path in paths
    )
    original_shape, solids, additional_shapes, shape_warnings = _combine_step_assembly_parts(
        parts, ocp=ocp
    )
    resolved_input_unit = _resolve_step_assembly_input_unit(parts, input_unit=input_unit)
    kernel_unit = _resolve_step_assembly_kernel_unit(
        parts,
        fallback_unit=resolved_input_unit,
    )
    warnings = tuple(warning for part in parts for warning in part.warnings) + shape_warnings
    component_names = tuple(name for part in parts for name in part.component_names)

    return PreparedStepInput(
        path=_assembly_path(paths),
        original_shape=original_shape,
        solids=solids,
        additional_shapes=additional_shapes,
        component_names=component_names,
        resolved_input_unit=resolved_input_unit,
        kernel_unit=kernel_unit,
        warnings=warnings,
        is_assembly=True,
    )


def _prepare_step_assembly_part(
    path: Path,
    *,
    input_unit: str,
    ocp: OcpBindings,
) -> PreparedStepAssemblyPart:
    read_result = _read_step_file(
        path,
        input_unit=input_unit,
        missing_unit_warning=f"Could not detect STEP length unit for {path.name}; assuming m.",
        ocp=ocp,
    )
    solids = tuple(
        _extract_ocp_solids(
            read_result.shape,
            TopAbs_SOLID=ocp.TopAbs_SOLID,
            TopExp_Explorer=ocp.TopExp_Explorer,
            TopoDS=ocp.TopoDS,
        )
    )
    if solids:
        non_solid_shapes = tuple(
            _extract_ocp_non_solid_faces(
                read_result.shape,
                solids,
                TopAbs_FACE=ocp.TopAbs_FACE,
                TopExp_Explorer=ocp.TopExp_Explorer,
            )
        )
    else:
        non_solid_shapes = (read_result.shape,)
    component_names = tuple(f"{path.name}: {name}" for name in _component_names(path, solids))
    declared_unit = (
        (
            _step_unit_name_to_length_unit(read_result.declared_unit_name)
            if read_result.declared_unit_name is not None
            else None
        )
        or read_result.declared_unit_name
        or read_result.resolved_input_unit
    )
    return PreparedStepAssemblyPart(
        path=path,
        shape=read_result.shape,
        solids=solids,
        non_solid_shapes=non_solid_shapes,
        component_names=component_names,
        declared_unit=declared_unit,
        resolved_input_unit=read_result.resolved_input_unit,
        kernel_unit=read_result.kernel_unit,
        warnings=read_result.warnings,
    )


def _combine_step_assembly_parts(
    parts: tuple[PreparedStepAssemblyPart, ...],
    *,
    ocp: OcpBindings,
) -> tuple[Any, tuple[Any, ...], tuple[Any, ...], tuple[str, ...]]:
    solids = tuple(solid for part in parts for solid in part.solids)
    non_solid_shapes = tuple(shape for part in parts for shape in part.non_solid_shapes)
    builder = ocp.BRep_Builder()
    original_shape = ocp.TopoDS_Compound()
    builder.MakeCompound(original_shape)
    if solids:
        for solid in solids:
            builder.Add(original_shape, solid)
        return original_shape, solids, non_solid_shapes, ()

    for shape in non_solid_shapes:
        builder.Add(original_shape, shape)
    return (
        original_shape,
        solids,
        (),
        ("STEP assembly did not contain solid components.",),
    )


def _resolve_step_assembly_input_unit(
    parts: tuple[PreparedStepAssemblyPart, ...],
    *,
    input_unit: str,
) -> str:
    if input_unit.strip().lower() != "auto":
        return normalize_unit(input_unit)
    unique_units = {part.declared_unit for part in parts}
    if len(unique_units) > 1:
        raise ValueError(
            "Cannot assemble STEP files with different detected units: "
            f"{', '.join(sorted(unique_units))}. "
            "Use files with a common unit or specify --unit explicitly."
        )
    return parts[0].resolved_input_unit if parts else "m"


def _resolve_step_assembly_kernel_unit(
    parts: tuple[PreparedStepAssemblyPart, ...],
    *,
    fallback_unit: str,
) -> str:
    unique_units = {part.kernel_unit for part in parts}
    if len(unique_units) > 1:
        raise ValueError("Cannot assemble STEP files with different kernel coordinate units.")
    return parts[0].kernel_unit if parts else fallback_unit


def _read_step_file(
    path: Path,
    *,
    input_unit: str,
    ocp: OcpBindings,
    missing_unit_warning: str = "Could not detect STEP length unit; assuming m.",
) -> ReadStepFile:
    reader = ocp.STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != ocp.IFSelect_RetDone:
        raise ValueError(f"Could not read STEP file: {path}")

    declared_unit_name = _step_length_unit_name(
        reader,
        TColStd_SequenceOfAsciiString=ocp.TColStd_SequenceOfAsciiString,
    )
    declared_input_unit = (
        None if declared_unit_name is None else _step_unit_name_to_length_unit(declared_unit_name)
    )
    declared_unit_mm = (
        None if declared_unit_name is None else _step_unit_name_to_millimetres(declared_unit_name)
    )
    warnings: list[str] = []
    coordinate_scale = 1.0
    if input_unit.strip().lower() == "auto":
        if declared_unit_name is None:
            resolved_input_unit = "m"
            kernel_unit = "mm"
            coordinate_scale = length_scale(resolved_input_unit, "mm")
            warnings.append(missing_unit_warning)
        elif declared_input_unit is None:
            resolved_input_unit = "mm"
            kernel_unit = "mm"
            warnings.append(
                f"STEP length unit '{declared_unit_name}' in {path.name} is not available "
                "as an input unit; OpenCascade converted it to mm."
            )
        else:
            resolved_input_unit = declared_input_unit
            kernel_unit = "mm"
        # Keep OpenCascade in its standard millimetre system. Its geometric
        # tolerances are expressed in kernel coordinates and become unreliable
        # for very small models if the kernel itself is switched to metres/feet.
    else:
        resolved_input_unit = normalize_unit(input_unit)
        kernel_unit = "mm"
        if declared_unit_name is not None and declared_unit_mm is None:
            raise ValueError(
                f"Cannot reinterpret STEP length unit '{declared_unit_name}' in "
                f"{path.name} as {resolved_input_unit}; its conversion factor is unsupported."
            )
        coordinate_scale = length_scale(resolved_input_unit, "mm") / (
            declared_unit_mm if declared_unit_mm is not None else 1.0
        )

    reader.SetSystemLengthUnit(1.0)
    transferred = reader.TransferRoots()
    if transferred == 0:
        raise ValueError(f"STEP file did not contain transferable roots: {path}")
    shape = reader.OneShape()
    if coordinate_scale != 1.0:
        transform = ocp.gp_Trsf()
        transform.SetScale(ocp.gp_Pnt(0.0, 0.0, 0.0), coordinate_scale)
        transformed = ocp.BRepBuilderAPI_Transform(shape, transform, True, False)
        if not transformed.IsDone():
            raise ValueError(f"Could not reinterpret STEP coordinates for {path}")
        shape = transformed.Shape()
    return ReadStepFile(
        shape=shape,
        declared_unit_name=declared_unit_name,
        resolved_input_unit=resolved_input_unit,
        kernel_unit=kernel_unit,
        warnings=tuple(warnings),
    )


def _component_names(path: Path, solids: tuple[Any, ...]) -> tuple[str, ...]:
    names = _step_component_names_from_xcaf(path, expected_count=len(solids))
    if names:
        return names
    return tuple(f"Component {index}" for index in range(1, len(solids) + 1))


def _finalize_step_model(
    prepared: PreparedStepInput,
    *,
    output_unit: str,
    mesh_deflection: float | str,
    angular_deflection: float,
    step_metric_source: str,
    step_components: tuple[int, ...] | None,
    step_component_mode: str,
    base_axis_map: str,
    base_tolerance: float,
    require_mesh: bool,
    ocp: OcpBindings,
) -> ModelData:
    options = StepFinalizationOptions(
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
        metric_source=normalize_step_metric_source(step_metric_source),
        step_components=step_components,
        step_component_mode=step_component_mode,
        base_axis_map=base_axis_map,
        base_tolerance=base_tolerance,
        require_mesh=require_mesh,
    )
    selected = _select_step_shape(prepared, options=options, ocp=ocp)
    geometry = _describe_step_geometry(
        prepared,
        selected,
        options=options,
        ocp=ocp,
    )
    exact_metrics = _calculate_exact_step_metrics(
        selected,
        geometry,
        options=options,
        ocp=ocp,
    )
    mesh = _tessellate_selected_step_shape(
        selected,
        geometry,
        angular_deflection=options.angular_deflection,
        must_tessellate=(
            options.require_mesh or options.metric_source == "mesh" or exact_metrics.base_failed
        ),
        ocp=ocp,
    )
    base_metric = _resolve_step_base_metric(
        exact_metrics,
        mesh,
        geometry,
        options=options,
    )
    native_metrics = _select_native_step_metrics(
        exact_metrics,
        mesh,
        selected,
        metric_source=options.metric_source,
        ocp=ocp,
    )
    validated_metrics = _validate_native_step_metrics(
        native_metrics,
        base_metric,
        selected,
        metric_source=options.metric_source,
    )
    scaled_metrics = _scale_step_metrics(
        validated_metrics,
        selected,
        metric_source=options.metric_source,
        kernel_unit=prepared.kernel_unit,
        output_unit=options.output_unit,
    )
    warnings = _final_step_warnings(
        prepared,
        selected.warnings,
        exact_metrics.warnings,
        base_metric.warnings,
        native_metrics.warnings,
        validated_metrics.warnings,
        scaled_metrics.warnings,
    )
    return _build_step_model_data(
        prepared,
        options=options,
        selected=selected,
        geometry=geometry,
        mesh=mesh,
        base_metric=base_metric,
        metrics=scaled_metrics,
        warnings=warnings,
    )


def _select_step_shape(
    prepared: PreparedStepInput,
    *,
    options: StepFinalizationOptions,
    ocp: OcpBindings,
) -> SelectedStepShape:
    warnings: list[str] = []
    solid_count = len(prepared.solids)
    selected_components = _resolve_step_component_selection(
        options.step_components,
        solid_count,
    )
    shape, unioned, retained_faces, cut_faces = _build_step_component_shape(
        prepared.original_shape,
        list(prepared.solids),
        selected_components,
        component_mode=options.step_component_mode,
        BRepAlgoAPI_Cut=ocp.BRepAlgoAPI_Cut,
        BRepAlgoAPI_Fuse=ocp.BRepAlgoAPI_Fuse,
        BRep_Builder=ocp.BRep_Builder,
        TopAbs_FACE=ocp.TopAbs_FACE,
        TopAbs_SOLID=ocp.TopAbs_SOLID,
        TopExp_Explorer=ocp.TopExp_Explorer,
        TopoDS=ocp.TopoDS,
        TopoDS_Compound=ocp.TopoDS_Compound,
    )
    if prepared.additional_shapes:
        if len(selected_components) == solid_count:
            builder = ocp.BRep_Builder()
            combined_shape = ocp.TopoDS_Compound()
            builder.MakeCompound(combined_shape)
            builder.Add(combined_shape, shape)
            for additional_shape in prepared.additional_shapes:
                builder.Add(combined_shape, additional_shape)
            shape = combined_shape
        else:
            warnings.append("Non-solid STEP inputs were excluded by solid component selection.")
    if unioned is None:
        subject = "STEP assembly solids" if prepared.is_assembly else "STEP solids"
        warnings.append(
            f"Could not boolean-union {subject}; volume and surface area may double-count overlaps."
        )
    empty_result = not _ocp_shape_has_subshape(
        shape,
        ocp.TopAbs_FACE,
        ocp.TopExp_Explorer,
    )
    topology_watertight = (
        False
        if empty_result
        else _ocp_shape_is_watertight(
            shape,
            BRepCheck_Analyzer=ocp.BRepCheck_Analyzer,
            BRep_Tool=ocp.BRep_Tool,
            TopAbs_FACE=ocp.TopAbs_FACE,
            TopAbs_SHELL=ocp.TopAbs_SHELL,
            TopAbs_SOLID=ocp.TopAbs_SOLID,
            TopExp_Explorer=ocp.TopExp_Explorer,
        )
    )
    subtraction_active = (
        options.step_component_mode == "subtract" and len(selected_components) < solid_count
    )
    retained_faces_tuple = None if retained_faces is None else tuple(retained_faces)
    cut_faces_tuple = None if cut_faces is None else tuple(cut_faces)
    return SelectedStepShape(
        shape=shape,
        selected_components=selected_components,
        retained_faces=retained_faces_tuple,
        cut_faces=cut_faces_tuple,
        empty_result=empty_result,
        topology_watertight=topology_watertight,
        subtraction_active=subtraction_active,
        face_classification_failed=subtraction_active and cut_faces is None,
        warnings=tuple(warnings),
    )


def _describe_step_geometry(
    prepared: PreparedStepInput,
    selected: SelectedStepShape,
    *,
    options: StepFinalizationOptions,
    ocp: OcpBindings,
) -> StepGeometry:
    scale = length_scale(prepared.kernel_unit, options.output_unit)
    empty_result = selected.empty_result
    native_bounds = (
        None
        if empty_result
        else _ocp_bounds(
            selected.shape,
            Bnd_Box=ocp.Bnd_Box,
            BRepBndLib=ocp.BRepBndLib,
        )
    )
    bounds = None if native_bounds is None else _scaled_output_bounds(native_bounds, scale)
    native_diagonal = (
        1.0
        if empty_result
        else _ocp_bounding_box_diagonal(
            selected.shape,
            Bnd_Box=ocp.Bnd_Box,
            BRepBndLib=ocp.BRepBndLib,
        )
    )
    mesh_deflection_value = _resolve_mesh_deflection(
        options.mesh_deflection,
        native_diagonal=native_diagonal,
        scale=scale,
    )
    native_mesh_deflection = (
        mesh_deflection_value / scale if scale != 0.0 else mesh_deflection_value
    )
    return StepGeometry(
        scale=scale,
        bounds=bounds,
        native_diagonal=native_diagonal,
        mesh_deflection=mesh_deflection_value,
        native_mesh_deflection=native_mesh_deflection,
    )


def _calculate_exact_step_metrics(
    selected: SelectedStepShape,
    geometry: StepGeometry,
    *,
    options: StepFinalizationOptions,
    ocp: OcpBindings,
) -> ExactStepMetrics:
    warnings: list[str] = []
    if selected.empty_result:
        exact_base_area, exact_base_found, exact_base_failed = 0.0, False, False
    elif selected.face_classification_failed:
        exact_base_area, exact_base_found, exact_base_failed = None, False, False
    else:
        exact_base_area, exact_base_found, exact_base_failed = _ocp_xmax_base_area(
            selected.shape,
            base_axis_map=options.base_axis_map,
            scale=geometry.scale,
            native_diagonal=geometry.native_diagonal,
            relative_tolerance=options.base_tolerance,
            Bnd_Box=ocp.Bnd_Box,
            BRepBndLib=ocp.BRepBndLib,
            BRepGProp=ocp.BRepGProp,
            GProp_GProps=ocp.GProp_GProps,
            TopAbs_FACE=ocp.TopAbs_FACE,
            TopExp_Explorer=ocp.TopExp_Explorer,
            TopoDS=ocp.TopoDS,
            excluded_faces=selected.cut_faces or (),
        )
    brep_volume = (
        0.0
        if selected.empty_result
        else _ocp_volume_metric_gk(
            selected.shape,
            GProp_GProps=ocp.GProp_GProps,
            BRepGProp=ocp.BRepGProp,
        )
    )
    brep_surface_area = (
        0.0
        if selected.empty_result
        else _ocp_shape_metric(
            selected.shape,
            ocp.GProp_GProps,
            ocp.BRepGProp,
            "SurfaceProperties",
        )
    )
    brep_newly_exposed_surface_area: float | None = None
    if selected.retained_faces is not None and selected.cut_faces is not None:
        brep_surface_area = _ocp_shapes_surface_area(
            selected.retained_faces,
            ocp.GProp_GProps,
            ocp.BRepGProp,
        )
        brep_newly_exposed_surface_area = _ocp_shapes_surface_area(
            selected.cut_faces,
            ocp.GProp_GProps,
            ocp.BRepGProp,
        )
    elif selected.subtraction_active:
        brep_surface_area = None
        warnings.append("Could not classify STEP cut faces; surface_area was left unset.")
    return ExactStepMetrics(
        volume=brep_volume,
        surface_area=brep_surface_area,
        newly_exposed_surface_area=brep_newly_exposed_surface_area,
        base_area=exact_base_area,
        base_found=exact_base_found,
        base_failed=exact_base_failed,
        warnings=tuple(warnings),
    )


def _tessellate_selected_step_shape(
    selected: SelectedStepShape,
    geometry: StepGeometry,
    *,
    angular_deflection: float,
    must_tessellate: bool,
    ocp: OcpBindings,
) -> TessellatedStepShape:
    if must_tessellate and not selected.empty_result:
        ocp.BRepMesh_IncrementalMesh(
            selected.shape,
            geometry.native_mesh_deflection,
            False,
            angular_deflection,
            True,
        )
        vertices, faces, newly_exposed_face_indices = _tessellate_ocp_shape_with_marked_faces(
            selected.shape,
            marked_faces=selected.cut_faces or (),
            BRep_Tool=ocp.BRep_Tool,
            TopAbs_FACE=ocp.TopAbs_FACE,
            TopAbs_REVERSED=ocp.TopAbs_REVERSED,
            TopExp_Explorer=ocp.TopExp_Explorer,
            TopLoc_Location=ocp.TopLoc_Location,
            TopoDS=ocp.TopoDS,
        )
    else:
        vertices, faces = _empty_mesh()
        newly_exposed_face_indices = ()
    return TessellatedStepShape(
        vertices=vertices,
        faces=faces,
        newly_exposed_face_indices=newly_exposed_face_indices,
    )


def _resolve_step_base_metric(
    exact_metrics: ExactStepMetrics,
    mesh: TessellatedStepShape,
    geometry: StepGeometry,
    *,
    options: StepFinalizationOptions,
) -> StepBaseMetric:
    warnings: list[str] = []
    base_area: float | None
    base_found: bool
    if exact_metrics.base_failed:
        base_area, base_found = _mesh_xmax_base_area(
            mesh.vertices,
            mesh.faces,
            base_axis_map=options.base_axis_map,
            scale=geometry.scale,
            native_diagonal=geometry.native_diagonal,
            relative_tolerance=options.base_tolerance,
            excluded_face_indices=mesh.newly_exposed_face_indices,
        )
        warnings.append("Could not calculate exact STEP base area; used tessellated mesh fallback.")
    else:
        base_area = exact_metrics.base_area
        base_found = exact_metrics.base_found
    return StepBaseMetric(area=base_area, found=base_found, warnings=tuple(warnings))


def _select_native_step_metrics(
    exact_metrics: ExactStepMetrics,
    mesh: TessellatedStepShape,
    selected: SelectedStepShape,
    *,
    metric_source: str,
    ocp: OcpBindings,
) -> NativeStepMetrics:
    warnings: list[str] = []
    volume: float | None
    surface_area: float | None
    newly_exposed_surface_area: float | None
    mesh_watertight: bool | None
    if metric_source == "mesh":
        if selected.empty_result:
            volume, surface_area, mesh_watertight = 0.0, 0.0, False
        else:
            volume, surface_area, mesh_watertight = _mesh_volume_and_surface_area(
                mesh.vertices,
                mesh.faces,
            )
        newly_exposed_surface_area = None
        if selected.retained_faces is not None and selected.cut_faces is not None:
            surface_area = _tessellated_ocp_shapes_surface_area(
                selected.retained_faces,
                BRep_Tool=ocp.BRep_Tool,
                TopAbs_FACE=ocp.TopAbs_FACE,
                TopAbs_REVERSED=ocp.TopAbs_REVERSED,
                TopExp_Explorer=ocp.TopExp_Explorer,
                TopLoc_Location=ocp.TopLoc_Location,
                TopoDS=ocp.TopoDS,
            )
            newly_exposed_surface_area = _tessellated_ocp_shapes_surface_area(
                selected.cut_faces,
                BRep_Tool=ocp.BRep_Tool,
                TopAbs_FACE=ocp.TopAbs_FACE,
                TopAbs_REVERSED=ocp.TopAbs_REVERSED,
                TopExp_Explorer=ocp.TopExp_Explorer,
                TopLoc_Location=ocp.TopLoc_Location,
                TopoDS=ocp.TopoDS,
            )
        elif selected.subtraction_active:
            surface_area = None
        warnings.append("STEP volume and surface area were calculated from the tessellated mesh.")
        if not mesh_watertight:
            warnings.append(
                "STEP tessellated mesh is not watertight; mesh volume may be unreliable."
            )
    else:
        volume = exact_metrics.volume
        surface_area = exact_metrics.surface_area
        newly_exposed_surface_area = exact_metrics.newly_exposed_surface_area
        mesh_watertight = None
    return NativeStepMetrics(
        volume=volume,
        surface_area=surface_area,
        newly_exposed_surface_area=newly_exposed_surface_area,
        mesh_watertight=mesh_watertight,
        warnings=tuple(warnings),
    )


def _validate_native_step_metrics(
    metrics: NativeStepMetrics,
    base_metric: StepBaseMetric,
    selected: SelectedStepShape,
    *,
    metric_source: str,
) -> ValidatedStepMetrics:
    warnings: list[str] = []
    volume = metrics.volume
    surface_area = metrics.surface_area
    if selected.empty_result:
        warnings.append("STEP component subtraction produced an empty shape.")
    elif not selected.topology_watertight:
        volume = None
        warnings.append(
            "STEP shape is open, invalid, or contains non-solid faces; volume was left unset."
        )

    metric_label = "mesh" if metric_source == "mesh" else "exact"
    if volume is None:
        warnings.append(f"Could not calculate {metric_label} STEP volume.")
    if surface_area is None:
        warnings.append(f"Could not calculate {metric_label} STEP surface area.")
    if selected.face_classification_failed:
        warnings.append("Could not classify newly exposed STEP faces; base_area was left unset.")
    elif not base_metric.found:
        if selected.subtraction_active:
            warnings.append(
                "No retained Xmax base face after excluding newly exposed surfaces; "
                "base_area set to 0."
            )
        else:
            warnings.append("Could not find an Xmax base face; base_area set to 0.")
    return ValidatedStepMetrics(
        volume=volume,
        surface_area=surface_area,
        newly_exposed_surface_area=metrics.newly_exposed_surface_area,
        mesh_watertight=metrics.mesh_watertight,
        warnings=tuple(warnings),
    )


def _scale_step_metrics(
    metrics: ValidatedStepMetrics,
    selected: SelectedStepShape,
    *,
    metric_source: str,
    kernel_unit: str,
    output_unit: str,
) -> ScaledStepMetrics:
    warnings: list[str] = []
    scaled_volume = (
        abs(metrics.volume) * volume_scale(kernel_unit, output_unit)
        if metrics.volume is not None
        else None
    )
    scaled_surface_area = (
        metrics.surface_area * area_scale(kernel_unit, output_unit)
        if metrics.surface_area is not None
        else None
    )
    scaled_newly_exposed_surface_area = (
        metrics.newly_exposed_surface_area * area_scale(kernel_unit, output_unit)
        if metrics.newly_exposed_surface_area is not None
        else None
    )
    is_watertight = None
    if not selected.topology_watertight:
        is_watertight = False
    elif metric_source == "mesh":
        is_watertight = metrics.mesh_watertight
    elif scaled_volume is not None:
        is_watertight = scaled_volume > 0.0
        if not is_watertight:
            warnings.append("STEP shape has zero volume; it may be open or surface-only geometry.")
    return ScaledStepMetrics(
        volume=scaled_volume,
        surface_area=scaled_surface_area,
        newly_exposed_surface_area=scaled_newly_exposed_surface_area,
        is_watertight=is_watertight,
        warnings=tuple(warnings),
    )


def _final_step_warnings(
    prepared: PreparedStepInput,
    *warning_groups: tuple[str, ...],
) -> tuple[str, ...]:
    warnings = prepared.warnings + tuple(warning for group in warning_groups for warning in group)
    return tuple(dict.fromkeys(warnings)) if prepared.is_assembly else warnings


def _build_step_model_data(
    prepared: PreparedStepInput,
    *,
    options: StepFinalizationOptions,
    selected: SelectedStepShape,
    geometry: StepGeometry,
    mesh: TessellatedStepShape,
    base_metric: StepBaseMetric,
    metrics: ScaledStepMetrics,
    warnings: tuple[str, ...],
) -> ModelData:
    return ModelData(
        path=prepared.path,
        source_format="step",
        vertices=mesh.vertices * geometry.scale,
        faces=mesh.faces,
        input_unit=normalize_unit(prepared.resolved_input_unit),
        output_unit=normalize_unit(options.output_unit),
        volume=metrics.volume,
        surface_area=metrics.surface_area,
        newly_exposed_surface_area=metrics.newly_exposed_surface_area,
        newly_exposed_face_indices=mesh.newly_exposed_face_indices,
        base_area=base_metric.area,
        is_watertight=metrics.is_watertight,
        mesh_deflection=geometry.mesh_deflection,
        angular_deflection=options.angular_deflection,
        base_tolerance=options.base_tolerance,
        step_metric_source=options.metric_source,
        step_component_mode=options.step_component_mode,
        is_assembly=prepared.is_assembly,
        component_names=prepared.component_names,
        selected_components=selected.selected_components,
        bounds=geometry.bounds,
        warnings=warnings,
    )


def _resolve_mesh_deflection(
    value: float | str,
    *,
    native_diagonal: float,
    scale: float,
) -> float:
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "auto":
            output_diagonal = native_diagonal * scale
            return max(output_diagonal * 1.0e-4, 1.0e-9)
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError("mesh_deflection must be a number or 'auto'") from exc
    if not isfinite(float(value)):
        raise ValueError("mesh_deflection must be finite")
    if value <= 0.0:
        raise ValueError("mesh_deflection must be greater than zero")
    return float(value)
