from __future__ import annotations

import argparse
import functools
import json
import math
import tempfile
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any

import cadmetrics._ocp as ocp_module
import cadmetrics._step_io as step_io_module
from cadmetrics.api import inspect_model

TIMED_STAGES = (
    "_boolean_union_ocp_solids",
    "_extract_ocp_non_solid_faces",
    "_ocp_shape_is_watertight",
)


def write_synthetic_assembly(path: Path, *, count: int, pitch: float = 30.0) -> None:
    """Write count solids in a sqrt(count) grid, cycling through four curved part shapes."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    from OCP.BRepPrimAPI import (
        BRepPrimAPI_MakeBox,
        BRepPrimAPI_MakeCylinder,
        BRepPrimAPI_MakeSphere,
        BRepPrimAPI_MakeTorus,
    )
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS, TopoDS_Compound
    from OCP.gp import gp_Pnt, gp_Trsf, gp_Vec

    def bored_cylinder() -> Any:
        outer = BRepPrimAPI_MakeCylinder(10.0, 20.0).Shape()
        inner = BRepPrimAPI_MakeCylinder(5.0, 20.0).Shape()
        return BRepAlgoAPI_Cut(outer, inner).Shape()

    def filleted_box() -> Any:
        box = BRepPrimAPI_MakeBox(gp_Pnt(-10.0, -10.0, 0.0), 20.0, 20.0, 20.0).Shape()
        fillet = BRepFilletAPI_MakeFillet(box)
        explorer = TopExp_Explorer(box, TopAbs_EDGE)
        while explorer.More():
            fillet.Add(3.0, TopoDS.Edge_s(explorer.Current()))
            explorer.Next()
        return fillet.Shape()

    makers: tuple[Callable[[], Any], ...] = (
        bored_cylinder,
        lambda: BRepPrimAPI_MakeSphere(11.0).Shape(),
        lambda: BRepPrimAPI_MakeTorus(9.0, 3.0).Shape(),
        filleted_box,
    )
    columns = math.ceil(math.sqrt(count))
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for index in range(count):
        row, column = divmod(index, columns)
        transform = gp_Trsf()
        transform.SetTranslation(gp_Vec(column * pitch, row * pitch, 0.0))
        part = BRepBuilderAPI_Transform(makers[index % len(makers)](), transform, True).Shape()
        builder.Add(compound, part)

    Interface_Static.SetCVal_s("write.step.unit", "MM")
    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"Could not write STEP file: {path}")


def _timed(name: str, original: Callable[..., Any], durations: dict[str, float]) -> Any:
    @functools.wraps(original)
    def timed(*args: Any, **kwargs: Any) -> Any:
        started = perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            durations[name] += perf_counter() - started

    return timed


def _install_stage_timers(durations: dict[str, float]) -> None:
    for name in TIMED_STAGES:
        timed = _timed(name, getattr(ocp_module, name), durations)
        for module in (ocp_module, step_io_module):
            if hasattr(module, name):
                setattr(module, name, timed)


def benchmark_step_load(path: Path) -> dict[str, Any]:
    durations: dict[str, float] = defaultdict(float)
    _install_stage_timers(durations)
    started = perf_counter()
    model = inspect_model(path)
    total = perf_counter() - started
    return {
        "file": str(path),
        "triangles": model.face_count,
        "volume": model.volume,
        "surface_area": model.surface_area,
        "total_seconds": total,
        "stage_seconds": {name: durations[name] for name in TIMED_STAGES},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark STEP loading on a synthetic assembly.")
    parser.add_argument("--parts", type=int, default=400)
    parser.add_argument("--output", type=Path, help="Keep the generated STEP file at this path.")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        path = args.output or Path(tmp) / f"assembly_{args.parts}.step"
        write_synthetic_assembly(path, count=args.parts)
        print(json.dumps(benchmark_step_load(path), indent=2))


if __name__ == "__main__":
    main()
