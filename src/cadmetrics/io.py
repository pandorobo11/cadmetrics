from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from cadmetrics._mesh_io import _load_stl, _load_stl_assembly
from cadmetrics._step_io import (
    _load_step,
    _load_step_assembly,
    _normalize_step_component_mode,
    _resolve_angular_deflection,
    _resolve_base_tolerance,
    _validate_mesh_deflection_input,
)
from cadmetrics.coordinates import DEFAULT_AXIS_MAP
from cadmetrics.types import ModelData

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
