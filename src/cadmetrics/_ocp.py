from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np

from cadmetrics._mesh_io import (
    _base_source_axis,
    _native_xmax_tolerance,
    _triangle_mesh_surface_area,
)


@dataclass(frozen=True)
class OcpBindings:
    Bnd_Box: Any
    BRep_Builder: Any
    BRep_Tool: Any
    BRepAlgoAPI_Cut: Any
    BRepAlgoAPI_Fuse: Any
    BRepBndLib: Any
    BRepCheck_Analyzer: Any
    BRepGProp: Any
    BRepMesh_IncrementalMesh: Any
    GProp_GProps: Any
    IFSelect_RetDone: Any
    STEPControl_Reader: Any
    TColStd_SequenceOfAsciiString: Any
    TopAbs_FACE: Any
    TopAbs_REVERSED: Any
    TopAbs_SHELL: Any
    TopAbs_SOLID: Any
    TopExp_Explorer: Any
    TopLoc_Location: Any
    TopoDS: Any
    TopoDS_Compound: Any


@cache
def load_ocp_bindings() -> OcpBindings:
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRep import BRep_Builder, BRep_Tool
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

    return OcpBindings(
        Bnd_Box=Bnd_Box,
        BRep_Builder=BRep_Builder,
        BRep_Tool=BRep_Tool,
        BRepAlgoAPI_Cut=BRepAlgoAPI_Cut,
        BRepAlgoAPI_Fuse=BRepAlgoAPI_Fuse,
        BRepBndLib=BRepBndLib,
        BRepCheck_Analyzer=BRepCheck_Analyzer,
        BRepGProp=BRepGProp,
        BRepMesh_IncrementalMesh=BRepMesh_IncrementalMesh,
        GProp_GProps=GProp_GProps,
        IFSelect_RetDone=IFSelect_RetDone,
        STEPControl_Reader=STEPControl_Reader,
        TColStd_SequenceOfAsciiString=TColStd_SequenceOfAsciiString,
        TopAbs_FACE=TopAbs_FACE,
        TopAbs_REVERSED=TopAbs_REVERSED,
        TopAbs_SHELL=TopAbs_SHELL,
        TopAbs_SOLID=TopAbs_SOLID,
        TopExp_Explorer=TopExp_Explorer,
        TopLoc_Location=TopLoc_Location,
        TopoDS=TopoDS,
        TopoDS_Compound=TopoDS_Compound,
    )


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
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return (
        float(xmin),
        float(ymin),
        float(zmin),
        float(xmax),
        float(ymax),
        float(zmax),
    )


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
    return (
        _clean_bound(xmin * scale),
        _clean_bound(xmax * scale),
        _clean_bound(ymin * scale),
        _clean_bound(ymax * scale),
        _clean_bound(zmin * scale),
        _clean_bound(zmax * scale),
    )


def _clean_bound(value: float) -> float:
    return 0.0 if abs(value) <= 1.0e-9 else value


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
