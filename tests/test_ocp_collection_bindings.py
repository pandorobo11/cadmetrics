from __future__ import annotations

import builtins
import importlib.util
import sys
from types import ModuleType

import pytest

from cadmetrics._ocp import load_ocp_bindings

requires_ocp = pytest.mark.skipif(
    importlib.util.find_spec("OCP") is None, reason="OCP is not installed"
)


@requires_ocp
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
    finally:
        load_ocp_bindings.cache_clear()


@pytest.mark.parametrize(
    ("import_error", "expected_message"),
    [
        (
            ModuleNotFoundError("No module named 'OCP'", name="OCP"),
            "STEP support requires the optional dependency: cadmetrics[step].",
        ),
        (
            ModuleNotFoundError("No module named 'OCP.Bnd'", name="OCP.Bnd"),
            "STEP support found OCP, but its required bindings could not be loaded:",
        ),
    ],
)
def test_step_binding_import_errors_identify_missing_extra_or_broken_install(
    monkeypatch: pytest.MonkeyPatch,
    import_error: ImportError,
    expected_message: str,
) -> None:
    original_import = builtins.__import__

    def fail_ocp_import(name, *args, **kwargs):
        if name == "OCP.Bnd":
            raise import_error
        return original_import(name, *args, **kwargs)

    load_ocp_bindings.cache_clear()
    monkeypatch.setattr(builtins, "__import__", fail_ocp_import)
    try:
        with pytest.raises(RuntimeError) as caught:
            load_ocp_bindings()
        assert expected_message in str(caught.value)
        assert caught.value.__cause__ is import_error
        if import_error.name != "OCP":
            assert str(import_error) in str(caught.value)
            assert "requires the optional dependency" not in str(caught.value)
    finally:
        load_ocp_bindings.cache_clear()
