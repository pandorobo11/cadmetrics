from __future__ import annotations

import sys
from types import ModuleType

import pytest

pytest.importorskip("OCP")

from cadmetrics._ocp import _OcpShapeSet, load_ocp_bindings


def test_shape_collection_bindings_preserve_shape_identity() -> None:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf, gp_Vec

    ocp = load_ocp_bindings()
    shape = BRepPrimAPI_MakeBox(1.0, 2.0, 3.0).Shape()
    shapes = ocp.TopTools_ListOfShape()
    shapes.Append(shape)
    assert shapes.First().IsSame(shape)

    shape_set = _OcpShapeSet([shape])
    assert shape.Reversed() in shape_set
    assert shape_set.add(shape.Reversed()) is False
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(10.0, 0.0, 0.0))
    moved = shape.Moved(TopLoc_Location(transform))
    assert moved not in shape_set
    assert shape_set.add(moved) is True


def test_shape_collection_bindings_accept_ocp8_exports(monkeypatch: pytest.MonkeyPatch) -> None:
    # Exercise the OCP 8 import path even in the locked OCP 7 test environment.
    native = load_ocp_bindings()
    collections = ModuleType("OCP.collections")
    collections.List_TopoDS_Shape = native.TopTools_ListOfShape
    collections.Map_TopoDS_Shape_TopTools_ShapeMapHasher = native.TopTools_MapOfShape
    collections.Sequence_TCollection_AsciiString = native.TColStd_SequenceOfAsciiString
    load_ocp_bindings.cache_clear()
    try:
        with monkeypatch.context() as patch:
            patch.setitem(sys.modules, "OCP.TopTools", ModuleType("OCP.TopTools"))
            patch.setitem(sys.modules, "OCP.collections", collections)
            ocp = load_ocp_bindings()
            assert ocp.TopTools_ListOfShape is native.TopTools_ListOfShape
            assert ocp.TopTools_MapOfShape is native.TopTools_MapOfShape
            test_shape_collection_bindings_preserve_shape_identity()
    finally:
        load_ocp_bindings.cache_clear()
