from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from cadmetrics.types import ModelData
from cadmetrics.units import area_scale, length_scale, normalize_unit, volume_scale

STEP_SUFFIXES = {".step", ".stp"}
STL_SUFFIXES = {".stl"}


def load_model(
    path: str | Path,
    *,
    input_unit: str = "auto",
    output_unit: str = "m",
    mesh_deflection: float = 1.0e-3,
    angular_deflection: float = 0.1,
) -> ModelData:
    model_path = Path(path)
    suffix = model_path.suffix.lower()
    if suffix in STL_SUFFIXES:
        return _load_stl(model_path, input_unit=input_unit, output_unit=output_unit)
    if suffix in STEP_SUFFIXES:
        return _load_step(
            model_path,
            input_unit=input_unit,
            output_unit=output_unit,
            mesh_deflection=mesh_deflection,
            angular_deflection=angular_deflection,
        )
    raise ValueError(f"Unsupported file type '{model_path.suffix}'. Expected STL or STEP.")


def _load_stl(path: Path, *, input_unit: str, output_unit: str) -> ModelData:
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
    return ModelData(
        path=path,
        source_format="stl",
        vertices=np.asarray(mesh.vertices, dtype=float) * scale,
        faces=np.asarray(mesh.faces, dtype=np.int64),
        input_unit=normalize_unit(resolved_input_unit),
        output_unit=normalize_unit(output_unit),
        volume=volume,
        surface_area=surface_area,
        is_watertight=is_watertight,
        warnings=tuple(warnings),
    )


def _load_step(
    path: Path,
    *,
    input_unit: str,
    output_unit: str,
    mesh_deflection: float,
    angular_deflection: float,
) -> ModelData:
    try:
        from OCP.BRep import BRep_Tool
        from OCP.BRepGProp import BRepGProp
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.GProp import GProp_GProps
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_Reader
        from OCP.TColStd import TColStd_SequenceOfAsciiString
        from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS
    except ImportError as exc:
        raise RuntimeError("STEP support requires the optional dependency: cadmetrics[step].") from exc

    reader = STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise ValueError(f"Could not read STEP file: {path}")
    transferred = reader.TransferRoots()
    if transferred == 0:
        raise ValueError(f"STEP file did not contain transferable roots: {path}")

    shape = reader.OneShape()
    warnings: list[str] = []
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
    native_mesh_deflection = mesh_deflection / scale if scale != 0.0 else mesh_deflection

    volume = _ocp_shape_metric(shape, GProp_GProps, BRepGProp, "VolumeProperties")
    surface_area = _ocp_shape_metric(shape, GProp_GProps, BRepGProp, "SurfaceProperties")

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

    if volume is None:
        warnings.append("Could not calculate exact STEP volume.")
    if surface_area is None:
        warnings.append("Could not calculate exact STEP surface area.")

    scaled_volume = (
        abs(volume) * volume_scale(resolved_input_unit, output_unit) if volume is not None else None
    )
    scaled_surface_area = (
        surface_area * area_scale(resolved_input_unit, output_unit)
        if surface_area is not None
        else None
    )
    is_watertight = None
    if scaled_volume is not None:
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
        is_watertight=is_watertight,
        warnings=tuple(warnings),
    )


def _ocp_shape_metric(shape: Any, props_type: Any, gprop_type: Any, method_name: str) -> float | None:
    props = props_type()
    method = getattr(gprop_type, f"{method_name}_s", None) or getattr(gprop_type, method_name, None)
    if method is None:
        return None
    try:
        method(shape, props)
        return float(props.Mass())
    except Exception:
        return None


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
