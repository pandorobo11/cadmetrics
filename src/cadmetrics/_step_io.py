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
from cadmetrics.types import ModelData
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
    warnings: list[str] = []
    declared_units: list[str] = []
    resolved_units: list[str] = []
    kernel_units: list[str] = []
    component_names: list[str] = []
    solids_by_component: list[Any] = []
    non_solid_shapes: list[Any] = []

    for path in paths:
        read_result = _read_step_file(
            path,
            input_unit=input_unit,
            missing_unit_warning=(
                f"Could not detect STEP length unit for {path.name}; assuming m."
            ),
            ocp=ocp,
        )
        original_shape = read_result.shape
        solids = tuple(
            _extract_ocp_solids(
                original_shape,
                TopAbs_SOLID=ocp.TopAbs_SOLID,
                TopExp_Explorer=ocp.TopExp_Explorer,
                TopoDS=ocp.TopoDS,
            )
        )
        warnings.extend(read_result.warnings)
        declared_units.append(
            (
                _step_unit_name_to_length_unit(read_result.declared_unit_name)
                if read_result.declared_unit_name is not None
                else None
            )
            or read_result.declared_unit_name
            or read_result.resolved_input_unit
        )
        resolved_units.append(read_result.resolved_input_unit)
        kernel_units.append(read_result.kernel_unit)

        for name, solid in zip(_component_names(path, solids), solids, strict=True):
            component_names.append(f"{path.name}: {name}")
            solids_by_component.append(solid)

        if solids:
            non_solid_shapes.extend(
                _extract_ocp_non_solid_faces(
                    original_shape,
                    solids,
                    TopAbs_FACE=ocp.TopAbs_FACE,
                    TopExp_Explorer=ocp.TopExp_Explorer,
                )
            )
        else:
            non_solid_shapes.append(original_shape)

    builder = ocp.BRep_Builder()
    original_shape = ocp.TopoDS_Compound()
    builder.MakeCompound(original_shape)
    if solids_by_component:
        for solid in solids_by_component:
            builder.Add(original_shape, solid)
    elif non_solid_shapes:
        for shape_item in non_solid_shapes:
            builder.Add(original_shape, shape_item)
        warnings.append("STEP assembly did not contain solid components.")
    else:
        warnings.append("STEP assembly did not contain solid components.")

    if input_unit.strip().lower() == "auto":
        unique_units = set(declared_units)
        if len(unique_units) > 1:
            raise ValueError(
                "Cannot assemble STEP files with different detected units: "
                f"{', '.join(sorted(unique_units))}. "
                "Use files with a common unit or specify --unit explicitly."
            )
        resolved_input_unit = resolved_units[0] if resolved_units else "m"
    else:
        resolved_input_unit = normalize_unit(input_unit)

    unique_kernel_units = set(kernel_units)
    if len(unique_kernel_units) > 1:
        raise ValueError("Cannot assemble STEP files with different kernel coordinate units.")
    kernel_unit = kernel_units[0] if kernel_units else resolved_input_unit

    return PreparedStepInput(
        path=_assembly_path(paths),
        original_shape=original_shape,
        solids=tuple(solids_by_component),
        additional_shapes=tuple(non_solid_shapes) if solids_by_component else (),
        component_names=tuple(component_names),
        resolved_input_unit=resolved_input_unit,
        kernel_unit=kernel_unit,
        warnings=tuple(warnings),
        is_assembly=True,
    )


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
        None
        if declared_unit_name is None
        else _step_unit_name_to_length_unit(declared_unit_name)
    )
    declared_unit_mm = (
        None
        if declared_unit_name is None
        else _step_unit_name_to_millimetres(declared_unit_name)
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
    metric_source = _normalize_step_metric_source(step_metric_source)
    warnings = list(prepared.warnings)
    solid_count = len(prepared.solids)
    selected_components = _resolve_step_component_selection(step_components, solid_count)
    shape, unioned, retained_faces, cut_faces = _build_step_component_shape(
        prepared.original_shape,
        list(prepared.solids),
        selected_components,
        component_mode=step_component_mode,
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
            f"Could not boolean-union {subject}; "
            "volume and surface area may double-count overlaps."
        )

    empty_result = not _ocp_shape_has_subshape(
        shape,
        ocp.TopAbs_FACE,
        ocp.TopExp_Explorer,
    )
    topology_watertight = False if empty_result else _ocp_shape_is_watertight(
        shape,
        BRepCheck_Analyzer=ocp.BRepCheck_Analyzer,
        BRep_Tool=ocp.BRep_Tool,
        TopAbs_FACE=ocp.TopAbs_FACE,
        TopAbs_SHELL=ocp.TopAbs_SHELL,
        TopAbs_SOLID=ocp.TopAbs_SOLID,
        TopExp_Explorer=ocp.TopExp_Explorer,
    )

    scale = length_scale(prepared.kernel_unit, output_unit)
    native_bounds = None if empty_result else _ocp_bounds(
        shape,
        Bnd_Box=ocp.Bnd_Box,
        BRepBndLib=ocp.BRepBndLib,
    )
    bounds = None if native_bounds is None else _scaled_output_bounds(native_bounds, scale)
    native_diagonal = 1.0 if empty_result else _ocp_bounding_box_diagonal(
        shape,
        Bnd_Box=ocp.Bnd_Box,
        BRepBndLib=ocp.BRepBndLib,
    )
    mesh_deflection_value = _resolve_mesh_deflection(
        mesh_deflection,
        native_diagonal=native_diagonal,
        scale=scale,
    )
    native_mesh_deflection = (
        mesh_deflection_value / scale if scale != 0.0 else mesh_deflection_value
    )

    subtraction_active = (
        step_component_mode == "subtract" and len(selected_components) < solid_count
    )
    face_classification_failed = subtraction_active and cut_faces is None
    if empty_result:
        exact_base_area, exact_base_found, exact_base_failed = 0.0, False, False
    elif face_classification_failed:
        exact_base_area, exact_base_found, exact_base_failed = None, False, False
    else:
        exact_base_area, exact_base_found, exact_base_failed = _ocp_xmax_base_area(
            shape,
            base_axis_map=base_axis_map,
            scale=scale,
            native_diagonal=native_diagonal,
            relative_tolerance=base_tolerance,
            Bnd_Box=ocp.Bnd_Box,
            BRepBndLib=ocp.BRepBndLib,
            BRepGProp=ocp.BRepGProp,
            GProp_GProps=ocp.GProp_GProps,
            TopAbs_FACE=ocp.TopAbs_FACE,
            TopExp_Explorer=ocp.TopExp_Explorer,
            TopoDS=ocp.TopoDS,
            excluded_faces=cut_faces or (),
        )

    brep_volume = 0.0 if empty_result else _ocp_volume_metric_gk(
        shape,
        GProp_GProps=ocp.GProp_GProps,
        BRepGProp=ocp.BRepGProp,
    )
    brep_surface_area = 0.0 if empty_result else _ocp_shape_metric(
        shape,
        ocp.GProp_GProps,
        ocp.BRepGProp,
        "SurfaceProperties",
    )
    brep_newly_exposed_surface_area: float | None = None
    if retained_faces is not None and cut_faces is not None:
        brep_surface_area = _ocp_shapes_surface_area(
            retained_faces,
            ocp.GProp_GProps,
            ocp.BRepGProp,
        )
        brep_newly_exposed_surface_area = _ocp_shapes_surface_area(
            cut_faces,
            ocp.GProp_GProps,
            ocp.BRepGProp,
        )
    elif subtraction_active:
        brep_surface_area = None
        warnings.append("Could not classify STEP cut faces; surface_area was left unset.")

    must_tessellate = require_mesh or metric_source == "mesh" or exact_base_failed
    if must_tessellate and not empty_result:
        ocp.BRepMesh_IncrementalMesh(
            shape,
            native_mesh_deflection,
            False,
            angular_deflection,
            True,
        )
        vertices, faces, newly_exposed_face_indices = (
            _tessellate_ocp_shape_with_marked_faces(
                shape,
                marked_faces=cut_faces or (),
                BRep_Tool=ocp.BRep_Tool,
                TopAbs_FACE=ocp.TopAbs_FACE,
                TopAbs_REVERSED=ocp.TopAbs_REVERSED,
                TopExp_Explorer=ocp.TopExp_Explorer,
                TopLoc_Location=ocp.TopLoc_Location,
                TopoDS=ocp.TopoDS,
            )
        )
    else:
        vertices, faces = _empty_mesh()
        newly_exposed_face_indices = ()

    base_area: float | None
    base_found: bool
    if exact_base_failed:
        base_area, base_found = _mesh_xmax_base_area(
            vertices,
            faces,
            base_axis_map=base_axis_map,
            scale=scale,
            native_diagonal=native_diagonal,
            relative_tolerance=base_tolerance,
            excluded_face_indices=newly_exposed_face_indices,
        )
        warnings.append("Could not calculate exact STEP base area; used tessellated mesh fallback.")
    else:
        base_area = exact_base_area
        base_found = exact_base_found

    volume: float | None
    surface_area: float | None
    newly_exposed_surface_area: float | None
    mesh_watertight: bool | None
    if metric_source == "mesh":
        if empty_result:
            volume, surface_area, mesh_watertight = 0.0, 0.0, False
        else:
            volume, surface_area, mesh_watertight = _mesh_volume_and_surface_area(vertices, faces)
        newly_exposed_surface_area = None
        if retained_faces is not None and cut_faces is not None:
            surface_area = _tessellated_ocp_shapes_surface_area(
                retained_faces,
                BRep_Tool=ocp.BRep_Tool,
                TopAbs_FACE=ocp.TopAbs_FACE,
                TopAbs_REVERSED=ocp.TopAbs_REVERSED,
                TopExp_Explorer=ocp.TopExp_Explorer,
                TopLoc_Location=ocp.TopLoc_Location,
                TopoDS=ocp.TopoDS,
            )
            newly_exposed_surface_area = _tessellated_ocp_shapes_surface_area(
                cut_faces,
                BRep_Tool=ocp.BRep_Tool,
                TopAbs_FACE=ocp.TopAbs_FACE,
                TopAbs_REVERSED=ocp.TopAbs_REVERSED,
                TopExp_Explorer=ocp.TopExp_Explorer,
                TopLoc_Location=ocp.TopLoc_Location,
                TopoDS=ocp.TopoDS,
            )
        elif subtraction_active:
            surface_area = None
        warnings.append("STEP volume and surface area were calculated from the tessellated mesh.")
        if not mesh_watertight:
            warnings.append("STEP tessellated mesh is not watertight; mesh volume may be unreliable.")
    else:
        volume = brep_volume
        surface_area = brep_surface_area
        newly_exposed_surface_area = brep_newly_exposed_surface_area
        mesh_watertight = None

    if empty_result:
        warnings.append("STEP component subtraction produced an empty shape.")
    elif not topology_watertight:
        volume = None
        warnings.append(
            "STEP shape is open, invalid, or contains non-solid faces; volume was left unset."
        )

    metric_label = "mesh" if metric_source == "mesh" else "exact"
    if volume is None:
        warnings.append(f"Could not calculate {metric_label} STEP volume.")
    if surface_area is None:
        warnings.append(f"Could not calculate {metric_label} STEP surface area.")
    if face_classification_failed:
        warnings.append("Could not classify newly exposed STEP faces; base_area was left unset.")
    elif not base_found:
        if subtraction_active:
            warnings.append(
                "No retained Xmax base face after excluding newly exposed surfaces; "
                "base_area set to 0."
            )
        else:
            warnings.append("Could not find an Xmax base face; base_area set to 0.")

    scaled_volume = (
        abs(volume) * volume_scale(prepared.kernel_unit, output_unit)
        if volume is not None
        else None
    )
    scaled_surface_area = (
        surface_area * area_scale(prepared.kernel_unit, output_unit)
        if surface_area is not None
        else None
    )
    scaled_newly_exposed_surface_area = (
        newly_exposed_surface_area * area_scale(prepared.kernel_unit, output_unit)
        if newly_exposed_surface_area is not None
        else None
    )
    is_watertight = None
    if not topology_watertight:
        is_watertight = False
    elif metric_source == "mesh":
        is_watertight = mesh_watertight
    elif scaled_volume is not None:
        is_watertight = scaled_volume > 0.0
        if not is_watertight:
            warnings.append("STEP shape has zero volume; it may be open or surface-only geometry.")

    final_warnings = tuple(dict.fromkeys(warnings)) if prepared.is_assembly else tuple(warnings)
    return ModelData(
        path=prepared.path,
        source_format="step",
        vertices=vertices * scale,
        faces=faces,
        input_unit=normalize_unit(prepared.resolved_input_unit),
        output_unit=normalize_unit(output_unit),
        volume=scaled_volume,
        surface_area=scaled_surface_area,
        newly_exposed_surface_area=scaled_newly_exposed_surface_area,
        newly_exposed_face_indices=newly_exposed_face_indices,
        base_area=base_area,
        is_watertight=is_watertight,
        mesh_deflection=mesh_deflection_value,
        angular_deflection=angular_deflection,
        base_tolerance=base_tolerance,
        step_metric_source=metric_source,
        step_component_mode=step_component_mode,
        is_assembly=prepared.is_assembly,
        component_names=prepared.component_names,
        selected_components=selected_components,
        bounds=bounds,
        warnings=final_warnings,
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


def _validate_mesh_deflection_input(value: float | str) -> None:
    if isinstance(value, str) and value.strip().lower() == "auto":
        return
    try:
        deflection = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("mesh_deflection must be a number or 'auto'") from exc
    if not isfinite(deflection):
        raise ValueError("mesh_deflection must be finite")
    if deflection <= 0.0:
        raise ValueError("mesh_deflection must be greater than zero")


def _resolve_base_tolerance(value: float) -> float:
    try:
        tolerance = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("base_tolerance must be a number") from exc
    if not isfinite(tolerance):
        raise ValueError("base_tolerance must be finite")
    if tolerance <= 0.0:
        raise ValueError("base_tolerance must be greater than zero")
    return tolerance


def _resolve_angular_deflection(value: float) -> float:
    try:
        deflection = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("angular_deflection must be a number") from exc
    if not isfinite(deflection):
        raise ValueError("angular_deflection must be finite")
    if deflection < 0.0:
        raise ValueError("angular_deflection must not be negative")
    return deflection


def _normalize_step_metric_source(value: str) -> str:
    text = value.strip().lower().replace("_", "-")
    if text in {"brep", "b-rep", "exact", "kernel"}:
        return "brep"
    if text in {"mesh", "tessellated", "stl"}:
        return "mesh"
    raise ValueError("step_metric_source must be 'brep' or 'mesh'")


def _normalize_step_component_mode(value: str) -> str:
    text = value.strip().lower().replace("_", "-")
    if text in {"filter", "exclude", "hide"}:
        return "filter"
    if text in {"subtract", "cut", "difference"}:
        return "subtract"
    raise ValueError("step_component_mode must be 'filter' or 'subtract'")
