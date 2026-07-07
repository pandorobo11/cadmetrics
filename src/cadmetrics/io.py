from __future__ import annotations

from collections.abc import Sequence
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
    base_axis_map: str = DEFAULT_AXIS_MAP,
    base_tolerance: float = DEFAULT_BASE_TOLERANCE,
    require_mesh: bool = True,
) -> ModelData:
    base_tolerance = _resolve_base_tolerance(base_tolerance)
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
            base_axis_map=base_axis_map,
            base_tolerance=base_tolerance,
            require_mesh=require_mesh,
        )

    model_path = paths[0]
    suffix = model_path.suffix.lower()
    if suffix in STL_SUFFIXES:
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
    base_axis_map: str,
    base_tolerance: float,
    require_mesh: bool,
) -> ModelData:
    suffixes = {path.suffix.lower() for path in paths}
    if suffixes <= STL_SUFFIXES:
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
        warnings.append("Mesh is not watertight; volume may be unreliable.")

    volume = abs(float(mesh.volume)) * volume_scale(resolved_input_unit, output_unit)
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
    base_axis_map: str,
    base_tolerance: float,
    require_mesh: bool,
) -> ModelData:
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRep import BRep_Builder
        from OCP.BRep import BRep_Tool
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
        from OCP.BRepBndLib import BRepBndLib
        from OCP.BRepGProp import BRepGProp
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.GProp import GProp_GProps
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_Reader
        from OCP.TColStd import TColStd_SequenceOfAsciiString
        from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID
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
    shape = _shape_from_selected_components(
        original_shape,
        solids,
        selected_components,
        BRep_Builder=BRep_Builder,
        TopoDS_Compound=TopoDS_Compound,
    )
    shape, unioned = _boolean_union_ocp_solids(
        shape,
        BRepAlgoAPI_Fuse=BRepAlgoAPI_Fuse,
        TopAbs_SOLID=TopAbs_SOLID,
        TopExp_Explorer=TopExp_Explorer,
        TopoDS=TopoDS,
    )
    if unioned is None:
        warnings.append(
            "Could not boolean-union STEP solids; volume and surface area may double-count overlaps."
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
    native_bounds = _ocp_bounds(shape, Bnd_Box=Bnd_Box, BRepBndLib=BRepBndLib)
    bounds = _scaled_output_bounds(native_bounds, scale)
    native_diagonal = _ocp_bounding_box_diagonal(
        shape,
        Bnd_Box=Bnd_Box,
        BRepBndLib=BRepBndLib,
    )
    mesh_deflection_value = _resolve_mesh_deflection(
        mesh_deflection,
        native_diagonal=native_diagonal,
        scale=scale,
    )
    native_mesh_deflection = (
        mesh_deflection_value / scale if scale != 0.0 else mesh_deflection_value
    )

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
    )
    brep_volume = _ocp_volume_metric_gk(shape, GProp_GProps=GProp_GProps, BRepGProp=BRepGProp)
    brep_surface_area = _ocp_shape_metric(shape, GProp_GProps, BRepGProp, "SurfaceProperties")

    must_tessellate = require_mesh or metric_source == "mesh" or exact_base_failed
    if must_tessellate:
        BRepMesh_IncrementalMesh(shape, native_mesh_deflection, False, angular_deflection, True)
        vertices, faces = _tessellate_ocp_shape(
            shape,
            BRep_Tool=BRep_Tool,
            TopAbs_FACE=TopAbs_FACE,
            TopAbs_REVERSED=TopAbs_REVERSED,
            TopExp_Explorer=TopExp_Explorer,
            TopLoc_Location=TopLoc_Location,
            TopoDS=TopoDS,
        )
    else:
        vertices, faces = _empty_mesh()
    if exact_base_failed:
        base_area, base_found = _mesh_xmax_base_area(
            vertices,
            faces,
            base_axis_map=base_axis_map,
            scale=scale,
            native_diagonal=native_diagonal,
            relative_tolerance=base_tolerance,
        )
        warnings.append("Could not calculate exact STEP base area; used tessellated mesh fallback.")
    else:
        base_area = exact_base_area
        base_found = exact_base_found

    if metric_source == "mesh":
        volume, surface_area, mesh_watertight = _mesh_volume_and_surface_area(vertices, faces)
        warnings.append("STEP volume and surface area were calculated from the tessellated mesh.")
        if not mesh_watertight:
            warnings.append("STEP tessellated mesh is not watertight; mesh volume may be unreliable.")
    else:
        volume = brep_volume
        surface_area = brep_surface_area
        mesh_watertight = None

    metric_label = "mesh" if metric_source == "mesh" else "exact"
    if volume is None:
        warnings.append(f"Could not calculate {metric_label} STEP volume.")
    if surface_area is None:
        warnings.append(f"Could not calculate {metric_label} STEP surface area.")
    if not base_found:
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
    is_watertight = None
    if metric_source == "mesh":
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
        base_area=base_area,
        is_watertight=is_watertight,
        mesh_deflection=mesh_deflection_value,
        angular_deflection=angular_deflection,
        base_tolerance=base_tolerance,
        step_metric_source=metric_source,
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
    base_axis_map: str,
    base_tolerance: float,
    require_mesh: bool,
) -> ModelData:
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRep import BRep_Builder
        from OCP.BRep import BRep_Tool
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
        from OCP.BRepBndLib import BRepBndLib
        from OCP.BRepGProp import BRepGProp
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.GProp import GProp_GProps
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_Reader
        from OCP.TColStd import TColStd_SequenceOfAsciiString
        from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID
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
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    if solids_by_component:
        for component_index in selected_components:
            builder.Add(compound, solids_by_component[component_index - 1])
    elif non_solid_shapes:
        for shape_item in non_solid_shapes:
            builder.Add(compound, shape_item)
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

    shape, unioned = _boolean_union_ocp_solids(
        compound,
        BRepAlgoAPI_Fuse=BRepAlgoAPI_Fuse,
        TopAbs_SOLID=TopAbs_SOLID,
        TopExp_Explorer=TopExp_Explorer,
        TopoDS=TopoDS,
    )
    if unioned is None:
        warnings.append(
            "Could not boolean-union STEP assembly solids; volume and surface area may double-count overlaps."
        )

    scale = length_scale(resolved_input_unit, output_unit)
    native_bounds = _ocp_bounds(shape, Bnd_Box=Bnd_Box, BRepBndLib=BRepBndLib)
    bounds = _scaled_output_bounds(native_bounds, scale)
    native_diagonal = _ocp_bounding_box_diagonal(
        shape,
        Bnd_Box=Bnd_Box,
        BRepBndLib=BRepBndLib,
    )
    mesh_deflection_value = _resolve_mesh_deflection(
        mesh_deflection,
        native_diagonal=native_diagonal,
        scale=scale,
    )
    native_mesh_deflection = (
        mesh_deflection_value / scale if scale != 0.0 else mesh_deflection_value
    )

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
    )
    brep_volume = _ocp_volume_metric_gk(shape, GProp_GProps=GProp_GProps, BRepGProp=BRepGProp)
    brep_surface_area = _ocp_shape_metric(shape, GProp_GProps, BRepGProp, "SurfaceProperties")

    must_tessellate = require_mesh or metric_source == "mesh" or exact_base_failed
    if must_tessellate:
        BRepMesh_IncrementalMesh(shape, native_mesh_deflection, False, angular_deflection, True)
        vertices, faces = _tessellate_ocp_shape(
            shape,
            BRep_Tool=BRep_Tool,
            TopAbs_FACE=TopAbs_FACE,
            TopAbs_REVERSED=TopAbs_REVERSED,
            TopExp_Explorer=TopExp_Explorer,
            TopLoc_Location=TopLoc_Location,
            TopoDS=TopoDS,
        )
    else:
        vertices, faces = _empty_mesh()
    if exact_base_failed:
        base_area, base_found = _mesh_xmax_base_area(
            vertices,
            faces,
            base_axis_map=base_axis_map,
            scale=scale,
            native_diagonal=native_diagonal,
            relative_tolerance=base_tolerance,
        )
        warnings.append("Could not calculate exact STEP base area; used tessellated mesh fallback.")
    else:
        base_area = exact_base_area
        base_found = exact_base_found

    if metric_source == "mesh":
        volume, surface_area, mesh_watertight = _mesh_volume_and_surface_area(vertices, faces)
        warnings.append("STEP volume and surface area were calculated from the tessellated mesh.")
        if not mesh_watertight:
            warnings.append("STEP tessellated mesh is not watertight; mesh volume may be unreliable.")
    else:
        volume = brep_volume
        surface_area = brep_surface_area
        mesh_watertight = None

    metric_label = "mesh" if metric_source == "mesh" else "exact"
    if volume is None:
        warnings.append(f"Could not calculate {metric_label} STEP volume.")
    if surface_area is None:
        warnings.append(f"Could not calculate {metric_label} STEP surface area.")
    if not base_found:
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
    is_watertight = None
    if metric_source == "mesh":
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
        base_area=base_area,
        is_watertight=is_watertight,
        mesh_deflection=mesh_deflection_value,
        angular_deflection=angular_deflection,
        base_tolerance=base_tolerance,
        step_metric_source=metric_source,
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
    if value <= 0.0:
        raise ValueError("mesh_deflection must be greater than zero")
    return float(value)


def _resolve_base_tolerance(value: float) -> float:
    try:
        tolerance = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("base_tolerance must be a number") from exc
    if tolerance <= 0.0:
        raise ValueError("base_tolerance must be greater than zero")
    return tolerance


def _normalize_step_metric_source(value: str) -> str:
    text = value.strip().lower().replace("_", "-")
    if text in {"brep", "b-rep", "exact", "kernel"}:
        return "brep"
    if text in {"mesh", "tessellated", "stl"}:
        return "mesh"
    raise ValueError("step_metric_source must be 'brep' or 'mesh'")


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
    return max(diagonal, 1.0)


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
    rows: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
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
        for index in range(1, triangulation.NbTriangles() + 1):
            n1, n2, n3 = triangulation.Triangle(index).Get()
            if reversed_face:
                n2, n3 = n3, n2
            faces.append((base_index + n1 - 1, base_index + n2 - 1, base_index + n3 - 1))
        explorer.Next()

    return np.asarray(rows, dtype=float), np.asarray(faces, dtype=np.int64)


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
