from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np

from cadmetrics.coordinates import DEFAULT_AXIS_MAP, parse_axis_map
from cadmetrics.types import ModelData
from cadmetrics.units import area_scale, length_scale, normalize_unit, volume_scale

STEP_SUFFIXES = {".step", ".stp"}
STL_SUFFIXES = {".stl"}
DEFAULT_BASE_TOLERANCE = 1.0e-6


def load_model(
    path: str | Path | Sequence[str | Path],
    *,
    input_unit: str = "auto",
    output_unit: str = "m",
    mesh_deflection: float | str = "auto",
    angular_deflection: float = 0.1,
    step_metric_source: str = "brep",
    step_components: tuple[int, ...] | None = None,
    step_component_mode: str = "filter",
    base_axis_map: str = DEFAULT_AXIS_MAP,
    base_tolerance: float = DEFAULT_BASE_TOLERANCE,
    require_mesh: bool = True,
) -> ModelData:
    component_mode = _normalize_step_component_mode(step_component_mode)
    base_tolerance = _resolve_base_tolerance(base_tolerance)
    angular_deflection = _resolve_angular_deflection(angular_deflection)
    _validate_mesh_deflection_input(mesh_deflection)
    paths = _normalize_model_paths(path)
    if len(paths) > 1:
        return _load_assembly(
            paths,
            input_unit=input_unit,
            output_unit=output_unit,
            mesh_deflection=mesh_deflection,
            angular_deflection=angular_deflection,
            step_metric_source=step_metric_source,
            step_components=step_components,
            step_component_mode=component_mode,
            base_axis_map=base_axis_map,
            base_tolerance=base_tolerance,
            require_mesh=require_mesh,
        )

    model_path = paths[0]
    suffix = model_path.suffix.lower()
    if suffix in STL_SUFFIXES:
        if component_mode != "filter":
            raise ValueError("step_component_mode='subtract' is only available for STEP input.")
        return _load_stl(
            model_path,
            input_unit=input_unit,
            output_unit=output_unit,
            base_axis_map=base_axis_map,
            base_tolerance=base_tolerance,
        )
    if suffix in STEP_SUFFIXES:
        return _load_step(
            model_path,
            input_unit=input_unit,
            output_unit=output_unit,
            mesh_deflection=mesh_deflection,
            angular_deflection=angular_deflection,
            step_metric_source=step_metric_source,
            step_components=step_components,
            step_component_mode=component_mode,
            base_axis_map=base_axis_map,
            base_tolerance=base_tolerance,
            require_mesh=require_mesh,
        )
    raise ValueError(f"Unsupported file type '{model_path.suffix}'. Expected STL or STEP.")


def _normalize_model_paths(path: str | Path | Sequence[str | Path]) -> tuple[Path, ...]:
    if isinstance(path, str | Path):
        return (Path(path),)
    paths = tuple(Path(item) for item in path)
    if not paths:
        raise ValueError("At least one STL or STEP file is required.")
    return paths


def _load_assembly(
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
    suffixes = {path.suffix.lower() for path in paths}
    if suffixes <= STL_SUFFIXES:
        if step_component_mode != "filter":
            raise ValueError("step_component_mode='subtract' is only available for STEP input.")
        return _load_stl_assembly(
            paths,
            input_unit=input_unit,
            output_unit=output_unit,
            base_axis_map=base_axis_map,
            base_tolerance=base_tolerance,
        )
    if suffixes <= STEP_SUFFIXES:
        return _load_step_assembly(
            paths,
            input_unit=input_unit,
            output_unit=output_unit,
            mesh_deflection=mesh_deflection,
            angular_deflection=angular_deflection,
            step_metric_source=step_metric_source,
            step_components=step_components,
            step_component_mode=step_component_mode,
            base_axis_map=base_axis_map,
            base_tolerance=base_tolerance,
            require_mesh=require_mesh,
        )
    if suffixes & STL_SUFFIXES and suffixes & STEP_SUFFIXES:
        raise ValueError("Cannot assemble mixed STEP and STL inputs.")
    suffix_list = ", ".join(sorted(suffixes))
    raise ValueError(f"Unsupported file types for assembly: {suffix_list}")


def _load_stl(
    path: Path,
    *,
    input_unit: str,
    output_unit: str,
    base_axis_map: str,
    base_tolerance: float,
) -> ModelData:
    try:
        import trimesh
    except ImportError as exc:
        raise RuntimeError("STL support requires the 'trimesh' dependency.") from exc

    mesh = trimesh.load(path, force="mesh", process=False)
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    if isinstance(mesh, list):
        mesh = trimesh.util.concatenate(mesh)
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"Could not load STL mesh from {path}")
    mesh = mesh.copy()
    mesh.merge_vertices()

    resolved_input_unit = "m" if input_unit.strip().lower() == "auto" else input_unit
    scale = length_scale(resolved_input_unit, output_unit)
    warnings: list[str] = []
    is_watertight = bool(mesh.is_watertight)
    if not is_watertight:
        warnings.append("Mesh is not watertight; volume is unavailable.")

    volume = (
        abs(float(mesh.volume)) * volume_scale(resolved_input_unit, output_unit)
        if is_watertight
        else None
    )
    surface_area = float(mesh.area) * area_scale(resolved_input_unit, output_unit)
    native_vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    native_diagonal = _mesh_bounding_box_diagonal(native_vertices)
    base_area, base_found = _mesh_xmax_base_area(
        native_vertices,
        faces,
        base_axis_map=base_axis_map,
        scale=scale,
        native_diagonal=native_diagonal,
        relative_tolerance=base_tolerance,
    )
    if not base_found:
        warnings.append("Could not find an Xmax base face; base_area set to 0.")
    return ModelData(
        path=path,
        source_format="stl",
        vertices=native_vertices * scale,
        faces=faces,
        input_unit=normalize_unit(resolved_input_unit),
        output_unit=normalize_unit(output_unit),
        volume=volume,
        surface_area=surface_area,
        base_area=base_area,
        is_watertight=is_watertight,
        mesh_deflection=None,
        angular_deflection=None,
        base_tolerance=base_tolerance,
        warnings=tuple(warnings),
    )


def _load_stl_assembly(
    paths: tuple[Path, ...],
    *,
    input_unit: str,
    output_unit: str,
    base_axis_map: str,
    base_tolerance: float,
) -> ModelData:
    models = [
        _load_stl(
            path,
            input_unit=input_unit,
            output_unit=output_unit,
            base_axis_map=base_axis_map,
            base_tolerance=base_tolerance,
        )
        for path in paths
    ]
    vertices, faces = _combine_meshes(
        [(model.vertices, model.faces) for model in models]
    )
    volume, surface_area, is_watertight = _mesh_volume_and_surface_area(vertices, faces)
    if is_watertight is not True or any(model.is_watertight is not True for model in models):
        volume = None
    base_area, base_found = _mesh_xmax_base_area(
        vertices,
        faces,
        base_axis_map=base_axis_map,
        scale=1.0,
        native_diagonal=_mesh_bounding_box_diagonal(vertices),
        relative_tolerance=base_tolerance,
    )
    warnings = [
        "STL assembly meshes were concatenated without boolean union; overlapping volume and surface area may double-count."
    ]
    if not base_found:
        warnings.append("Could not find an Xmax base face; base_area set to 0.")
    for model in models:
        warnings.extend(model.warnings)

    return ModelData(
        path=_assembly_path(paths),
        source_format="stl",
        vertices=vertices,
        faces=faces,
        input_unit=models[0].input_unit,
        output_unit=normalize_unit(output_unit),
        volume=volume,
        surface_area=surface_area,
        base_area=base_area,
        is_watertight=is_watertight,
        mesh_deflection=None,
        angular_deflection=None,
        base_tolerance=base_tolerance,
        is_assembly=True,
        warnings=tuple(dict.fromkeys(warnings)),
    )


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
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRep import BRep_Builder
        from OCP.BRep import BRep_Tool
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
        from OCP.BRepBndLib import BRepBndLib
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.BRepGProp import BRepGProp
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.GProp import GProp_GProps
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_Reader
        from OCP.TColStd import TColStd_SequenceOfAsciiString
        from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SHELL, TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS, TopoDS_Compound
    except ImportError as exc:
        raise RuntimeError(
            "STEP support requires the optional dependency: cadmetrics[step]."
        ) from exc

    reader = STEPControl_Reader()
    metric_source = _normalize_step_metric_source(step_metric_source)
    status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise ValueError(f"Could not read STEP file: {path}")
    transferred = reader.TransferRoots()
    if transferred == 0:
        raise ValueError(f"STEP file did not contain transferable roots: {path}")

    original_shape = reader.OneShape()
    warnings: list[str] = []
    solids = _extract_ocp_solids(
        original_shape,
        TopAbs_SOLID=TopAbs_SOLID,
        TopExp_Explorer=TopExp_Explorer,
        TopoDS=TopoDS,
    )
    component_names = _step_component_names_from_xcaf(path, expected_count=len(solids))
    if not component_names:
        component_names = tuple(f"Component {index}" for index in range(1, len(solids) + 1))
    selected_components = _resolve_step_component_selection(step_components, len(solids))
    shape, unioned, retained_faces, cut_faces = _build_step_component_shape(
        original_shape,
        solids,
        selected_components,
        component_mode=step_component_mode,
        BRepAlgoAPI_Cut=BRepAlgoAPI_Cut,
        BRepAlgoAPI_Fuse=BRepAlgoAPI_Fuse,
        BRep_Builder=BRep_Builder,
        TopAbs_FACE=TopAbs_FACE,
        TopAbs_SOLID=TopAbs_SOLID,
        TopExp_Explorer=TopExp_Explorer,
        TopoDS=TopoDS,
        TopoDS_Compound=TopoDS_Compound,
    )
    if unioned is None:
        warnings.append(
            "Could not boolean-union STEP solids; volume and surface area may double-count overlaps."
        )
    empty_result = not _ocp_shape_has_subshape(shape, TopAbs_FACE, TopExp_Explorer)
    topology_watertight = False if empty_result else _ocp_shape_is_watertight(
        shape,
        BRepCheck_Analyzer=BRepCheck_Analyzer,
        BRep_Tool=BRep_Tool,
        TopAbs_FACE=TopAbs_FACE,
        TopAbs_SHELL=TopAbs_SHELL,
        TopAbs_SOLID=TopAbs_SOLID,
        TopExp_Explorer=TopExp_Explorer,
    )
    resolved_input_unit = input_unit
    if input_unit.strip().lower() == "auto":
        resolved_input_unit = _detect_step_length_unit(
            reader,
            TColStd_SequenceOfAsciiString=TColStd_SequenceOfAsciiString,
        )
        if resolved_input_unit is None:
            resolved_input_unit = "m"
            warnings.append("Could not detect STEP length unit; assuming m.")

    scale = length_scale(resolved_input_unit, output_unit)
    native_bounds = None if empty_result else _ocp_bounds(
        shape, Bnd_Box=Bnd_Box, BRepBndLib=BRepBndLib
    )
    bounds = None if native_bounds is None else _scaled_output_bounds(native_bounds, scale)
    native_diagonal = 1.0 if empty_result else _ocp_bounding_box_diagonal(
        shape, Bnd_Box=Bnd_Box, BRepBndLib=BRepBndLib
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
        step_component_mode == "subtract" and len(selected_components) < len(solids)
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
            Bnd_Box=Bnd_Box,
            BRepBndLib=BRepBndLib,
            BRepGProp=BRepGProp,
            GProp_GProps=GProp_GProps,
            TopAbs_FACE=TopAbs_FACE,
            TopExp_Explorer=TopExp_Explorer,
            TopoDS=TopoDS,
            excluded_faces=cut_faces or (),
        )
    brep_volume = 0.0 if empty_result else _ocp_volume_metric_gk(
        shape, GProp_GProps=GProp_GProps, BRepGProp=BRepGProp
    )
    brep_surface_area = 0.0 if empty_result else _ocp_shape_metric(
        shape, GProp_GProps, BRepGProp, "SurfaceProperties"
    )
    brep_newly_exposed_surface_area: float | None = None
    if retained_faces is not None and cut_faces is not None:
        brep_surface_area = _ocp_shapes_surface_area(retained_faces, GProp_GProps, BRepGProp)
        brep_newly_exposed_surface_area = _ocp_shapes_surface_area(
            cut_faces, GProp_GProps, BRepGProp
        )
    elif step_component_mode == "subtract" and len(selected_components) < len(solids):
        brep_surface_area = None
        warnings.append(
            "Could not classify STEP cut faces; surface_area was left unset."
        )

    must_tessellate = require_mesh or metric_source == "mesh" or exact_base_failed
    if must_tessellate and not empty_result:
        BRepMesh_IncrementalMesh(shape, native_mesh_deflection, False, angular_deflection, True)
        vertices, faces, newly_exposed_face_indices = (
            _tessellate_ocp_shape_with_marked_faces(
                shape,
                marked_faces=cut_faces or (),
                BRep_Tool=BRep_Tool,
                TopAbs_FACE=TopAbs_FACE,
                TopAbs_REVERSED=TopAbs_REVERSED,
                TopExp_Explorer=TopExp_Explorer,
                TopLoc_Location=TopLoc_Location,
                TopoDS=TopoDS,
            )
        )
    else:
        vertices, faces = _empty_mesh()
        newly_exposed_face_indices = ()
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

    if metric_source == "mesh":
        if empty_result:
            volume, surface_area, mesh_watertight = 0.0, 0.0, False
        else:
            volume, surface_area, mesh_watertight = _mesh_volume_and_surface_area(vertices, faces)
        newly_exposed_surface_area = None
        if retained_faces is not None and cut_faces is not None:
            surface_area = _tessellated_ocp_shapes_surface_area(
                retained_faces,
                BRep_Tool=BRep_Tool,
                TopAbs_FACE=TopAbs_FACE,
                TopAbs_REVERSED=TopAbs_REVERSED,
                TopExp_Explorer=TopExp_Explorer,
                TopLoc_Location=TopLoc_Location,
                TopoDS=TopoDS,
            )
            newly_exposed_surface_area = _tessellated_ocp_shapes_surface_area(
                cut_faces,
                BRep_Tool=BRep_Tool,
                TopAbs_FACE=TopAbs_FACE,
                TopAbs_REVERSED=TopAbs_REVERSED,
                TopExp_Explorer=TopExp_Explorer,
                TopLoc_Location=TopLoc_Location,
                TopoDS=TopoDS,
            )
        elif step_component_mode == "subtract" and len(selected_components) < len(solids):
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
        warnings.append(
            "Could not classify newly exposed STEP faces; base_area was left unset."
        )
    elif not base_found:
        if subtraction_active:
            warnings.append(
                "No retained Xmax base face after excluding newly exposed surfaces; "
                "base_area set to 0."
            )
        else:
            warnings.append("Could not find an Xmax base face; base_area set to 0.")

    scaled_volume = (
        abs(volume) * volume_scale(resolved_input_unit, output_unit)
        if volume is not None
        else None
    )
    scaled_surface_area = (
        surface_area * area_scale(resolved_input_unit, output_unit)
        if surface_area is not None
        else None
    )
    scaled_newly_exposed_surface_area = (
        newly_exposed_surface_area * area_scale(resolved_input_unit, output_unit)
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

    return ModelData(
        path=path,
        source_format="step",
        vertices=vertices * scale,
        faces=faces,
        input_unit=normalize_unit(resolved_input_unit),
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
        component_names=component_names,
        selected_components=selected_components,
        bounds=bounds,
        warnings=tuple(warnings),
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
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRep import BRep_Builder
        from OCP.BRep import BRep_Tool
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
        from OCP.BRepBndLib import BRepBndLib
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.BRepGProp import BRepGProp
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.GProp import GProp_GProps
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_Reader
        from OCP.TColStd import TColStd_SequenceOfAsciiString
        from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SHELL, TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS, TopoDS_Compound
    except ImportError as exc:
        raise RuntimeError(
            "STEP support requires the optional dependency: cadmetrics[step]."
        ) from exc

    metric_source = _normalize_step_metric_source(step_metric_source)
    warnings: list[str] = []
    detected_units: list[str] = []
    component_names: list[str] = []
    solids_by_component: list[Any] = []
    non_solid_shapes: list[Any] = []

    for path in paths:
        reader = STEPControl_Reader()
        status = reader.ReadFile(str(path))
        if status != IFSelect_RetDone:
            raise ValueError(f"Could not read STEP file: {path}")
        transferred = reader.TransferRoots()
        if transferred == 0:
            raise ValueError(f"STEP file did not contain transferable roots: {path}")

        original_shape = reader.OneShape()
        solids = _extract_ocp_solids(
            original_shape,
            TopAbs_SOLID=TopAbs_SOLID,
            TopExp_Explorer=TopExp_Explorer,
            TopoDS=TopoDS,
        )
        if input_unit.strip().lower() == "auto":
            detected = _detect_step_length_unit(
                reader,
                TColStd_SequenceOfAsciiString=TColStd_SequenceOfAsciiString,
            )
            if detected is None:
                detected = "m"
                warnings.append(f"Could not detect STEP length unit for {path.name}; assuming m.")
            detected_units.append(detected)

        names = _step_component_names_from_xcaf(path, expected_count=len(solids))
        if not names:
            names = tuple(f"Component {index}" for index in range(1, len(solids) + 1))
        for name, solid in zip(names, solids, strict=True):
            component_names.append(f"{path.name}: {name}")
            solids_by_component.append(solid)

        if solids:
            continue
        if step_components is None:
            non_solid_shapes.append(original_shape)

    selected_components = _resolve_step_component_selection(
        step_components,
        len(solids_by_component),
    )
    builder = BRep_Builder()
    original_shape = TopoDS_Compound()
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
        unique_units = set(detected_units)
        if len(unique_units) > 1:
            raise ValueError(
                "Cannot assemble STEP files with different detected units: "
                f"{', '.join(sorted(unique_units))}. "
                "Use files with a common unit or specify --unit explicitly."
            )
        resolved_input_unit = detected_units[0] if detected_units else "m"
    else:
        resolved_input_unit = input_unit

    shape, unioned, retained_faces, cut_faces = _build_step_component_shape(
        original_shape,
        solids_by_component,
        selected_components,
        component_mode=step_component_mode,
        BRepAlgoAPI_Cut=BRepAlgoAPI_Cut,
        BRepAlgoAPI_Fuse=BRepAlgoAPI_Fuse,
        BRep_Builder=BRep_Builder,
        TopAbs_FACE=TopAbs_FACE,
        TopAbs_SOLID=TopAbs_SOLID,
        TopExp_Explorer=TopExp_Explorer,
        TopoDS=TopoDS,
        TopoDS_Compound=TopoDS_Compound,
    )
    if unioned is None:
        warnings.append(
            "Could not boolean-union STEP assembly solids; volume and surface area may double-count overlaps."
        )
    empty_result = not _ocp_shape_has_subshape(shape, TopAbs_FACE, TopExp_Explorer)
    topology_watertight = False if empty_result else _ocp_shape_is_watertight(
        shape,
        BRepCheck_Analyzer=BRepCheck_Analyzer,
        BRep_Tool=BRep_Tool,
        TopAbs_FACE=TopAbs_FACE,
        TopAbs_SHELL=TopAbs_SHELL,
        TopAbs_SOLID=TopAbs_SOLID,
        TopExp_Explorer=TopExp_Explorer,
    )

    scale = length_scale(resolved_input_unit, output_unit)
    native_bounds = None if empty_result else _ocp_bounds(
        shape, Bnd_Box=Bnd_Box, BRepBndLib=BRepBndLib
    )
    bounds = None if native_bounds is None else _scaled_output_bounds(native_bounds, scale)
    native_diagonal = 1.0 if empty_result else _ocp_bounding_box_diagonal(
        shape, Bnd_Box=Bnd_Box, BRepBndLib=BRepBndLib
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
        step_component_mode == "subtract"
        and len(selected_components) < len(solids_by_component)
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
            Bnd_Box=Bnd_Box,
            BRepBndLib=BRepBndLib,
            BRepGProp=BRepGProp,
            GProp_GProps=GProp_GProps,
            TopAbs_FACE=TopAbs_FACE,
            TopExp_Explorer=TopExp_Explorer,
            TopoDS=TopoDS,
            excluded_faces=cut_faces or (),
        )
    brep_volume = 0.0 if empty_result else _ocp_volume_metric_gk(
        shape, GProp_GProps=GProp_GProps, BRepGProp=BRepGProp
    )
    brep_surface_area = 0.0 if empty_result else _ocp_shape_metric(
        shape, GProp_GProps, BRepGProp, "SurfaceProperties"
    )
    brep_newly_exposed_surface_area: float | None = None
    if retained_faces is not None and cut_faces is not None:
        brep_surface_area = _ocp_shapes_surface_area(retained_faces, GProp_GProps, BRepGProp)
        brep_newly_exposed_surface_area = _ocp_shapes_surface_area(
            cut_faces, GProp_GProps, BRepGProp
        )
    elif step_component_mode == "subtract" and len(selected_components) < len(solids_by_component):
        brep_surface_area = None
        warnings.append(
            "Could not classify STEP cut faces; surface_area was left unset."
        )

    must_tessellate = require_mesh or metric_source == "mesh" or exact_base_failed
    if must_tessellate and not empty_result:
        BRepMesh_IncrementalMesh(shape, native_mesh_deflection, False, angular_deflection, True)
        vertices, faces, newly_exposed_face_indices = (
            _tessellate_ocp_shape_with_marked_faces(
                shape,
                marked_faces=cut_faces or (),
                BRep_Tool=BRep_Tool,
                TopAbs_FACE=TopAbs_FACE,
                TopAbs_REVERSED=TopAbs_REVERSED,
                TopExp_Explorer=TopExp_Explorer,
                TopLoc_Location=TopLoc_Location,
                TopoDS=TopoDS,
            )
        )
    else:
        vertices, faces = _empty_mesh()
        newly_exposed_face_indices = ()
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

    if metric_source == "mesh":
        if empty_result:
            volume, surface_area, mesh_watertight = 0.0, 0.0, False
        else:
            volume, surface_area, mesh_watertight = _mesh_volume_and_surface_area(vertices, faces)
        newly_exposed_surface_area = None
        if retained_faces is not None and cut_faces is not None:
            surface_area = _tessellated_ocp_shapes_surface_area(
                retained_faces,
                BRep_Tool=BRep_Tool,
                TopAbs_FACE=TopAbs_FACE,
                TopAbs_REVERSED=TopAbs_REVERSED,
                TopExp_Explorer=TopExp_Explorer,
                TopLoc_Location=TopLoc_Location,
                TopoDS=TopoDS,
            )
            newly_exposed_surface_area = _tessellated_ocp_shapes_surface_area(
                cut_faces,
                BRep_Tool=BRep_Tool,
                TopAbs_FACE=TopAbs_FACE,
                TopAbs_REVERSED=TopAbs_REVERSED,
                TopExp_Explorer=TopExp_Explorer,
                TopLoc_Location=TopLoc_Location,
                TopoDS=TopoDS,
            )
        elif (
            step_component_mode == "subtract"
            and len(selected_components) < len(solids_by_component)
        ):
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
        warnings.append(
            "Could not classify newly exposed STEP faces; base_area was left unset."
        )
    elif not base_found:
        if subtraction_active:
            warnings.append(
                "No retained Xmax base face after excluding newly exposed surfaces; "
                "base_area set to 0."
            )
        else:
            warnings.append("Could not find an Xmax base face; base_area set to 0.")

    scaled_volume = (
        abs(volume) * volume_scale(resolved_input_unit, output_unit)
        if volume is not None
        else None
    )
    scaled_surface_area = (
        surface_area * area_scale(resolved_input_unit, output_unit)
        if surface_area is not None
        else None
    )
    scaled_newly_exposed_surface_area = (
        newly_exposed_surface_area * area_scale(resolved_input_unit, output_unit)
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

    return ModelData(
        path=_assembly_path(paths),
        source_format="step",
        vertices=vertices * scale,
        faces=faces,
        input_unit=normalize_unit(resolved_input_unit),
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
        is_assembly=True,
        component_names=tuple(component_names),
        selected_components=tuple(selected_components),
        bounds=bounds,
        warnings=tuple(dict.fromkeys(warnings)),
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


def _mesh_volume_and_surface_area(
    vertices: np.ndarray,
    faces: np.ndarray,
) -> tuple[float | None, float | None, bool]:
    try:
        import trimesh
    except ImportError as exc:
        raise RuntimeError("Mesh metric mode requires the 'trimesh' dependency.") from exc

    if vertices.size == 0 or faces.size == 0:
        return None, None, False

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.merge_vertices()
    return abs(float(mesh.volume)), float(mesh.area), bool(mesh.is_watertight)


def _mesh_xmax_base_area(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    base_axis_map: str,
    scale: float,
    native_diagonal: float,
    relative_tolerance: float,
    excluded_face_indices: Sequence[int] = (),
) -> tuple[float, bool]:
    if vertices.size == 0 or faces.size == 0:
        return 0.0, False

    source_axis, sign = _base_source_axis(base_axis_map)
    coordinates = vertices[:, source_axis]
    target = float(np.max(coordinates) if sign > 0.0 else np.min(coordinates))
    tolerance = _native_xmax_tolerance(
        native_diagonal=native_diagonal,
        scale=scale,
        relative_tolerance=relative_tolerance,
    )
    face_coordinates = coordinates[faces]
    on_base = np.all(np.abs(face_coordinates - target) <= tolerance, axis=1)
    for face_index in excluded_face_indices:
        if 0 <= face_index < on_base.shape[0]:
            on_base[face_index] = False
    if not bool(np.any(on_base)):
        return 0.0, False

    triangles = vertices[faces[on_base]]
    native_area = float(
        np.sum(
            0.5
            * np.linalg.norm(
                np.cross(
                    triangles[:, 1] - triangles[:, 0],
                    triangles[:, 2] - triangles[:, 0],
                ),
                axis=1,
            )
        )
    )
    return native_area * scale * scale, native_area > 0.0


def _mesh_bounding_box_diagonal(vertices: np.ndarray) -> float:
    if vertices.size == 0:
        return 0.0
    extents = np.max(vertices, axis=0) - np.min(vertices, axis=0)
    return float(np.linalg.norm(extents))


def _combine_meshes(meshes: Sequence[tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    offset = 0
    for mesh_vertices, mesh_faces in meshes:
        vertices.append(mesh_vertices)
        faces.append(mesh_faces + offset)
        offset += int(mesh_vertices.shape[0])
    if not vertices:
        return np.empty((0, 3), dtype=float), np.empty((0, 3), dtype=np.int64)
    return np.vstack(vertices), np.vstack(faces).astype(np.int64, copy=False)


def _empty_mesh() -> tuple[np.ndarray, np.ndarray]:
    return np.empty((0, 3), dtype=float), np.empty((0, 3), dtype=np.int64)


def _assembly_path(paths: Sequence[Path]) -> Path:
    return Path("; ".join(str(path) for path in paths))


def _ocp_bounding_box_diagonal(
    shape: Any,
    *,
    Bnd_Box: Any,
    BRepBndLib: Any,
) -> float:
    box = Bnd_Box()
    _add_ocp_bounds(shape, box, BRepBndLib)
    try:
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    except Exception:
        return 1.0
    diagonal = float(np.linalg.norm([xmax - xmin, ymax - ymin, zmax - zmin]))
    return diagonal if isfinite(diagonal) and diagonal >= 0.0 else 1.0


def _ocp_xmax_base_area(
    shape: Any,
    *,
    base_axis_map: str,
    scale: float,
    native_diagonal: float,
    relative_tolerance: float,
    Bnd_Box: Any,
    BRepBndLib: Any,
    BRepGProp: Any,
    GProp_GProps: Any,
    TopAbs_FACE: Any,
    TopExp_Explorer: Any,
    TopoDS: Any,
    excluded_faces: Sequence[Any] = (),
) -> tuple[float, bool, bool]:
    try:
        source_axis, sign = _base_source_axis(base_axis_map)
        tolerance = _native_xmax_tolerance(
            native_diagonal=native_diagonal,
            scale=scale,
            relative_tolerance=relative_tolerance,
        )
        shape_bounds = _ocp_bounds(shape, Bnd_Box=Bnd_Box, BRepBndLib=BRepBndLib)
        target = shape_bounds[source_axis + 3] if sign > 0.0 else shape_bounds[source_axis]
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        face_method = getattr(TopoDS, "Face_s", None) or getattr(TopoDS, "Face")
        native_area = 0.0
        found = False

        while explorer.More():
            face = face_method(explorer.Current())
            if _contains_same_ocp_shape(excluded_faces, face):
                explorer.Next()
                continue
            face_bounds = _ocp_bounds(face, Bnd_Box=Bnd_Box, BRepBndLib=BRepBndLib)
            face_min = face_bounds[source_axis]
            face_max = face_bounds[source_axis + 3]
            if abs(face_min - target) <= tolerance and abs(face_max - target) <= tolerance:
                area = _ocp_shape_metric(face, GProp_GProps, BRepGProp, "SurfaceProperties")
                if area is None:
                    return 0.0, False, True
                if area > 0.0:
                    found = True
                    native_area += area
            explorer.Next()
        return native_area * scale * scale, found, False
    except Exception:
        return 0.0, False, True


def _ocp_bounds(
    shape: Any,
    *,
    Bnd_Box: Any,
    BRepBndLib: Any,
) -> tuple[float, float, float, float, float, float]:
    box = Bnd_Box()
    _add_ocp_bounds(shape, box, BRepBndLib)
    return tuple(float(value) for value in box.Get())


def _add_ocp_bounds(shape: Any, box: Any, BRepBndLib: Any) -> None:
    add_optimal = getattr(BRepBndLib, "AddOptimal_s", None) or getattr(
        BRepBndLib, "AddOptimal", None
    )
    if add_optimal is not None:
        try:
            add_optimal(shape, box, False, False)
            return
        except Exception:
            pass
    add_method = getattr(BRepBndLib, "Add_s", None) or getattr(BRepBndLib, "Add")
    add_method(shape, box)


def _scaled_output_bounds(
    native_bounds: tuple[float, float, float, float, float, float],
    scale: float,
) -> tuple[float, float, float, float, float, float]:
    xmin, ymin, zmin, xmax, ymax, zmax = native_bounds
    return tuple(
        _clean_bound(value)
        for value in (
            xmin * scale,
            xmax * scale,
            ymin * scale,
            ymax * scale,
            zmin * scale,
            zmax * scale,
        )
    )  # type: ignore[return-value]


def _clean_bound(value: float) -> float:
    return 0.0 if abs(value) <= 1.0e-9 else value


def _base_source_axis(base_axis_map: str) -> tuple[int, float]:
    return parse_axis_map(base_axis_map)[0]


def _native_xmax_tolerance(
    *,
    native_diagonal: float,
    scale: float,
    relative_tolerance: float,
) -> float:
    if scale <= 0.0:
        return max(native_diagonal * relative_tolerance, 1.0e-12)
    output_tolerance = max(native_diagonal * scale * relative_tolerance, 1.0e-12)
    return output_tolerance / scale


def _boolean_union_ocp_solids(
    shape: Any,
    *,
    BRepAlgoAPI_Fuse: Any,
    TopAbs_SOLID: Any,
    TopExp_Explorer: Any,
    TopoDS: Any,
) -> tuple[Any, bool | None]:
    solids = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    solid_method = getattr(TopoDS, "Solid_s", None) or getattr(TopoDS, "Solid")

    while explorer.More():
        solids.append(solid_method(explorer.Current()))
        explorer.Next()

    if len(solids) <= 1:
        return shape, False

    fused = solids[0]
    for solid in solids[1:]:
        fuse = BRepAlgoAPI_Fuse(fused, solid)
        if hasattr(fuse, "SetRunParallel"):
            fuse.SetRunParallel(True)
        fuse.Build()
        if not fuse.IsDone():
            return shape, None
        try:
            fuse.SimplifyResult(True, True, 1.0e-7)
        except Exception:
            pass
        fused = fuse.Shape()

    return fused, True


def _ocp_shape_is_watertight(
    shape: Any,
    *,
    BRepCheck_Analyzer: Any,
    BRep_Tool: Any,
    TopAbs_FACE: Any,
    TopAbs_SHELL: Any,
    TopAbs_SOLID: Any,
    TopExp_Explorer: Any,
) -> bool:
    try:
        if not BRepCheck_Analyzer(shape).IsValid():
            return False
    except Exception:
        return False

    solids = _explore_ocp_subshapes(shape, TopAbs_SOLID, TopExp_Explorer)
    if not solids:
        return False

    solid_faces: list[Any] = []
    for solid in solids:
        try:
            if not BRepCheck_Analyzer(solid).IsValid():
                return False
        except Exception:
            return False
        shells = _explore_ocp_subshapes(solid, TopAbs_SHELL, TopExp_Explorer)
        if not shells:
            return False
        try:
            if any(not BRep_Tool.IsClosed_s(shell) for shell in shells):
                return False
        except Exception:
            return False
        solid_faces.extend(_explore_ocp_subshapes(solid, TopAbs_FACE, TopExp_Explorer))

    all_faces = _explore_ocp_subshapes(shape, TopAbs_FACE, TopExp_Explorer)
    return all(any(face.IsSame(solid_face) for solid_face in solid_faces) for face in all_faces)


def _explore_ocp_subshapes(shape: Any, shape_type: Any, TopExp_Explorer: Any) -> list[Any]:
    subshapes: list[Any] = []
    explorer = TopExp_Explorer(shape, shape_type)
    while explorer.More():
        subshapes.append(explorer.Current())
        explorer.Next()
    return subshapes


def _ocp_shape_has_subshape(shape: Any, shape_type: Any, TopExp_Explorer: Any) -> bool:
    try:
        explorer = TopExp_Explorer(shape, shape_type)
        return bool(explorer.More())
    except Exception:
        return False


def _ocp_shapes_surface_area(
    shapes: Sequence[Any], GProp_GProps: Any, BRepGProp: Any
) -> float | None:
    total = 0.0
    for shape in shapes:
        area = _ocp_shape_metric(shape, GProp_GProps, BRepGProp, "SurfaceProperties")
        if area is None:
            return None
        total += area
    return total


def _extract_ocp_solids(
    shape: Any,
    *,
    TopAbs_SOLID: Any,
    TopExp_Explorer: Any,
    TopoDS: Any,
) -> list[Any]:
    solids = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    solid_method = getattr(TopoDS, "Solid_s", None) or getattr(TopoDS, "Solid")

    while explorer.More():
        solids.append(solid_method(explorer.Current()))
        explorer.Next()
    return solids


def _resolve_step_component_selection(
    step_components: tuple[int, ...] | None,
    component_count: int,
) -> tuple[int, ...]:
    if component_count == 0:
        if step_components is not None:
            raise ValueError("STEP component selection is only available for solid components.")
        return ()
    if step_components is None:
        return tuple(range(1, component_count + 1))

    selected = tuple(dict.fromkeys(int(index) for index in step_components))
    if not selected:
        raise ValueError("Select at least one STEP component.")
    invalid = [index for index in selected if index < 1 or index > component_count]
    if invalid:
        raise ValueError(
            "STEP component index out of range: "
            f"{', '.join(str(index) for index in invalid)} "
            f"(available: 1..{component_count})"
        )
    return selected


def _shape_from_selected_components(
    original_shape: Any,
    solids: list[Any],
    selected_components: tuple[int, ...],
    *,
    BRep_Builder: Any,
    TopoDS_Compound: Any,
) -> Any:
    if not selected_components or len(selected_components) == len(solids):
        return original_shape
    if len(selected_components) == 1:
        return solids[selected_components[0] - 1]

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for component_index in selected_components:
        builder.Add(compound, solids[component_index - 1])
    return compound


def _build_step_component_shape(
    original_shape: Any,
    solids: list[Any],
    selected_components: tuple[int, ...],
    *,
    component_mode: str,
    BRepAlgoAPI_Cut: Any,
    BRepAlgoAPI_Fuse: Any,
    BRep_Builder: Any,
    TopAbs_FACE: Any,
    TopAbs_SOLID: Any,
    TopExp_Explorer: Any,
    TopoDS: Any,
    TopoDS_Compound: Any,
) -> tuple[Any, bool | None, list[Any] | None, list[Any] | None]:
    enabled_shape = _shape_from_selected_components(
        original_shape,
        solids,
        selected_components,
        BRep_Builder=BRep_Builder,
        TopoDS_Compound=TopoDS_Compound,
    )
    enabled_shape, unioned = _boolean_union_ocp_solids(
        enabled_shape,
        BRepAlgoAPI_Fuse=BRepAlgoAPI_Fuse,
        TopAbs_SOLID=TopAbs_SOLID,
        TopExp_Explorer=TopExp_Explorer,
        TopoDS=TopoDS,
    )
    if component_mode == "filter" or not solids or len(selected_components) == len(solids):
        return enabled_shape, unioned, None, None
    if unioned is None:
        raise ValueError(
            "Could not boolean-union enabled STEP components before subtraction: "
            f"{', '.join(str(index) for index in selected_components)}"
        )

    selected = set(selected_components)
    disabled_components = tuple(
        index for index in range(1, len(solids) + 1) if index not in selected
    )
    disabled_shape = _shape_from_selected_components(
        original_shape,
        solids,
        disabled_components,
        BRep_Builder=BRep_Builder,
        TopoDS_Compound=TopoDS_Compound,
    )
    disabled_shape, disabled_unioned = _boolean_union_ocp_solids(
        disabled_shape,
        BRepAlgoAPI_Fuse=BRepAlgoAPI_Fuse,
        TopAbs_SOLID=TopAbs_SOLID,
        TopExp_Explorer=TopExp_Explorer,
        TopoDS=TopoDS,
    )
    if disabled_unioned is None:
        raise ValueError(
            "Could not boolean-union disabled STEP components before subtraction: "
            f"{', '.join(str(index) for index in disabled_components)}"
        )

    cut = BRepAlgoAPI_Cut(enabled_shape, disabled_shape)
    if hasattr(cut, "SetRunParallel"):
        cut.SetRunParallel(True)
    if hasattr(cut, "SetToFillHistory"):
        cut.SetToFillHistory(True)
    cut.Build()
    if not cut.IsDone():
        raise ValueError(
            "Could not subtract disabled STEP components: "
            f"{', '.join(str(index) for index in disabled_components)}"
        )

    result = cut.Shape()
    retained_faces, cut_faces = _classify_cut_result_faces(
        enabled_shape,
        result,
        cut,
        TopAbs_FACE=TopAbs_FACE,
        TopExp_Explorer=TopExp_Explorer,
    )
    return result, unioned, retained_faces, cut_faces


def _classify_cut_result_faces(
    source_shape: Any,
    result_shape: Any,
    cut: Any,
    *,
    TopAbs_FACE: Any,
    TopExp_Explorer: Any,
) -> tuple[list[Any] | None, list[Any] | None]:
    if hasattr(cut, "HasHistory") and not cut.HasHistory():
        return None, None

    result_faces = _explore_ocp_subshapes(result_shape, TopAbs_FACE, TopExp_Explorer)
    retained_faces: list[Any] = []
    source_faces = _explore_ocp_subshapes(source_shape, TopAbs_FACE, TopExp_Explorer)
    try:
        for source_face in source_faces:
            modified = list(cut.Modified(source_face))
            if modified:
                for face in modified:
                    _append_unique_ocp_shape(retained_faces, face)
            elif not cut.IsDeleted(source_face):
                _append_unique_ocp_shape(retained_faces, source_face)
    except Exception:
        return None, None

    if any(not _contains_same_ocp_shape(result_faces, face) for face in retained_faces):
        return None, None
    generated_faces = [
        face for face in result_faces if not _contains_same_ocp_shape(retained_faces, face)
    ]
    return retained_faces, generated_faces


def _append_unique_ocp_shape(shapes: list[Any], candidate: Any) -> None:
    if not _contains_same_ocp_shape(shapes, candidate):
        shapes.append(candidate)


def _contains_same_ocp_shape(shapes: Sequence[Any], candidate: Any) -> bool:
    return any(shape.IsSame(candidate) for shape in shapes)


def _step_component_names_from_xcaf(path: Path, *, expected_count: int) -> tuple[str, ...]:
    if expected_count == 0:
        return ()
    try:
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPCAFControl import STEPCAFControl_Reader
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Name
        from OCP.TDF import TDF_Label, TDF_LabelSequence
        from OCP.TDocStd import TDocStd_Document
        from OCP.TopAbs import TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer
        from OCP.XCAFApp import XCAFApp_Application
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
    except ImportError:
        return ()

    try:
        app = XCAFApp_Application.GetApplication_s()
        doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
        app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        if reader.ReadFile(str(path)) != IFSelect_RetDone:
            return ()
        if not reader.Transfer(doc):
            return ()
        shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        free_shapes = TDF_LabelSequence()
        shape_tool.GetFreeShapes(free_shapes)
        name_id = TDataStd_Name.GetID_s()
    except Exception:
        return ()

    def label_name(label: Any) -> str | None:
        try:
            attr = TDataStd_Name()
            if label.FindAttribute(name_id, attr):
                return _usable_step_component_name(attr.Get().ToExtString())
        except Exception:
            return None
        return None

    def referred_label(label: Any) -> Any | None:
        try:
            referred = TDF_Label()
            if shape_tool.GetReferredShape_s(label, referred) and not referred.IsNull():
                return referred
        except Exception:
            return None
        return None

    def solid_count(label: Any) -> int:
        try:
            shape = shape_tool.GetShape_s(label)
            explorer = TopExp_Explorer(shape, TopAbs_SOLID)
            count = 0
            while explorer.More():
                count += 1
                explorer.Next()
            return count
        except Exception:
            return 0

    def collect(label: Any, inherited_names: tuple[str, ...]) -> list[str | None]:
        own_name = label_name(label)
        ref = referred_label(label)
        ref_name = label_name(ref) if ref is not None else None
        names = tuple(name for name in (*inherited_names, own_name, ref_name) if name)

        components = TDF_LabelSequence()
        try:
            shape_tool.GetComponents_s(label, components)
        except Exception:
            components = TDF_LabelSequence()
        if components.Length() > 0:
            collected: list[str | None] = []
            for index in range(1, components.Length() + 1):
                collected.extend(collect(components.Value(index), names))
            return collected

        count = solid_count(label)
        if count == 0 and ref is not None:
            count = solid_count(ref)
        if count == 0:
            return []

        base_name = names[-1] if names else None
        if count == 1:
            return [base_name]
        if base_name is None:
            return [None] * count
        return [f"{base_name} #{index}" for index in range(1, count + 1)]

    names: list[str | None] = []
    for index in range(1, free_shapes.Length() + 1):
        names.extend(collect(free_shapes.Value(index), ()))

    if len(names) != expected_count:
        return ()
    return tuple(name or f"Component {index}" for index, name in enumerate(names, start=1))


def _usable_step_component_name(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return None
    if text.lower().startswith("open cascade step translator"):
        return None
    return text


def _ocp_shape_metric(
    shape: Any, props_type: Any, gprop_type: Any, method_name: str
) -> float | None:
    props = props_type()
    method = getattr(gprop_type, f"{method_name}_s", None) or getattr(
        gprop_type, method_name, None
    )
    if method is None:
        return None
    try:
        method(shape, props)
        return float(props.Mass())
    except Exception:
        return None


def _ocp_volume_metric_gk(shape: Any, *, GProp_GProps: Any, BRepGProp: Any) -> float | None:
    props = GProp_GProps()
    method = getattr(BRepGProp, "VolumePropertiesGK_s", None) or getattr(
        BRepGProp, "VolumePropertiesGK", None
    )
    if method is None:
        return _ocp_shape_metric(shape, GProp_GProps, BRepGProp, "VolumeProperties")

    try:
        error = method(shape, props, 1.0e-3, False, True, False, False, False)
        if error is not None and error < 0.0:
            return _ocp_shape_metric(shape, GProp_GProps, BRepGProp, "VolumeProperties")
        return float(props.Mass())
    except Exception:
        return _ocp_shape_metric(shape, GProp_GProps, BRepGProp, "VolumeProperties")


def _tessellate_ocp_shape(
    shape: Any,
    *,
    BRep_Tool: Any,
    TopAbs_FACE: Any,
    TopAbs_REVERSED: Any,
    TopExp_Explorer: Any,
    TopLoc_Location: Any,
    TopoDS: Any,
) -> tuple[np.ndarray, np.ndarray]:
    vertices, faces, _marked_face_indices = _tessellate_ocp_shape_with_marked_faces(
        shape,
        marked_faces=(),
        BRep_Tool=BRep_Tool,
        TopAbs_FACE=TopAbs_FACE,
        TopAbs_REVERSED=TopAbs_REVERSED,
        TopExp_Explorer=TopExp_Explorer,
        TopLoc_Location=TopLoc_Location,
        TopoDS=TopoDS,
    )
    return vertices, faces


def _tessellate_ocp_shape_with_marked_faces(
    shape: Any,
    *,
    marked_faces: Sequence[Any],
    BRep_Tool: Any,
    TopAbs_FACE: Any,
    TopAbs_REVERSED: Any,
    TopExp_Explorer: Any,
    TopLoc_Location: Any,
    TopoDS: Any,
) -> tuple[np.ndarray, np.ndarray, tuple[int, ...]]:
    rows: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    marked_face_indices: list[int] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    triangulation_method = getattr(BRep_Tool, "Triangulation_s", None) or getattr(
        BRep_Tool, "Triangulation"
    )
    face_method = getattr(TopoDS, "Face_s", None) or getattr(TopoDS, "Face")

    while explorer.More():
        face = face_method(explorer.Current())
        location = TopLoc_Location()
        triangulation = triangulation_method(face, location)
        if triangulation is None:
            explorer.Next()
            continue

        transform = location.Transformation()
        base_index = len(rows)
        for index in range(1, triangulation.NbNodes() + 1):
            point = triangulation.Node(index).Transformed(transform)
            rows.append((float(point.X()), float(point.Y()), float(point.Z())))

        reversed_face = face.Orientation() == TopAbs_REVERSED
        marked = _contains_same_ocp_shape(marked_faces, face)
        for index in range(1, triangulation.NbTriangles() + 1):
            n1, n2, n3 = triangulation.Triangle(index).Get()
            if reversed_face:
                n2, n3 = n3, n2
            if marked:
                marked_face_indices.append(len(faces))
            faces.append((base_index + n1 - 1, base_index + n2 - 1, base_index + n3 - 1))
        explorer.Next()

    return (
        np.asarray(rows, dtype=float),
        np.asarray(faces, dtype=np.int64),
        tuple(marked_face_indices),
    )


def _tessellated_ocp_shapes_surface_area(
    shapes: Sequence[Any],
    *,
    BRep_Tool: Any,
    TopAbs_FACE: Any,
    TopAbs_REVERSED: Any,
    TopExp_Explorer: Any,
    TopLoc_Location: Any,
    TopoDS: Any,
) -> float:
    total = 0.0
    for shape in shapes:
        vertices, faces = _tessellate_ocp_shape(
            shape,
            BRep_Tool=BRep_Tool,
            TopAbs_FACE=TopAbs_FACE,
            TopAbs_REVERSED=TopAbs_REVERSED,
            TopExp_Explorer=TopExp_Explorer,
            TopLoc_Location=TopLoc_Location,
            TopoDS=TopoDS,
        )
        total += _triangle_mesh_surface_area(vertices, faces)
    return total


def _triangle_mesh_surface_area(vertices: np.ndarray, faces: np.ndarray) -> float:
    if vertices.size == 0 or faces.size == 0:
        return 0.0
    triangles = vertices[faces]
    return float(
        np.sum(
            0.5
            * np.linalg.norm(
                np.cross(
                    triangles[:, 1] - triangles[:, 0],
                    triangles[:, 2] - triangles[:, 0],
                ),
                axis=1,
            )
        )
    )


def _detect_step_length_unit(
    reader: Any,
    *,
    TColStd_SequenceOfAsciiString: Any,
) -> str | None:
    lengths = TColStd_SequenceOfAsciiString()
    angles = TColStd_SequenceOfAsciiString()
    solid_angles = TColStd_SequenceOfAsciiString()
    try:
        reader.FileUnits(lengths, angles, solid_angles)
    except Exception:
        return None

    units = [
        lengths.Value(index).ToCString().strip().lower()
        for index in range(1, lengths.Length() + 1)
    ]
    if not units:
        return None

    return _step_unit_name_to_length_unit(units[0])


def _step_unit_name_to_length_unit(unit_name: str) -> str | None:
    normalized = unit_name.replace("_", " ").replace("-", " ").strip().lower()
    mapping = {
        "metre": "m",
        "meter": "m",
        "m": "m",
        "millimetre": "mm",
        "millimeter": "mm",
        "mm": "mm",
        "centimetre": "cm",
        "centimeter": "cm",
        "cm": "cm",
        "inch": "in",
        "in": "in",
        "foot": "ft",
        "feet": "ft",
        "ft": "ft",
    }
    return mapping.get(normalized)
