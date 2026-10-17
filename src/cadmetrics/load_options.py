from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Literal

from cadmetrics.coordinates import parse_axis_map
from cadmetrics.units import normalize_unit


DEFAULT_BASE_TOLERANCE = 1.0e-6
StepComponentMode = Literal["filter", "subtract"]
StepMetricSource = Literal["brep", "mesh"]


@dataclass(frozen=True)
class ModelLoadOptions:
    input_unit: str = "auto"
    output_unit: str = "m"
    mesh_deflection: float | str = "auto"
    angular_deflection: float = 0.1
    axis_map: str = "x,y,z"
    step_metric_source: StepMetricSource = "brep"
    step_components: tuple[int, ...] | None = None
    step_component_mode: StepComponentMode = "filter"
    base_tolerance: float = DEFAULT_BASE_TOLERANCE
    require_mesh: bool = True

    @classmethod
    def resolve(
        cls,
        *,
        input_unit: str = "auto",
        output_unit: str = "m",
        mesh_deflection: float | str = "auto",
        angular_deflection: float = 0.1,
        axis_map: str = "x,y,z",
        step_metric_source: str = "brep",
        step_components: tuple[int, ...] | None = None,
        step_component_mode: str = "filter",
        base_tolerance: float = DEFAULT_BASE_TOLERANCE,
        require_mesh: bool = True,
    ) -> ModelLoadOptions:
        input_text = input_unit.strip().lower()
        resolved_input_unit = "auto" if input_text == "auto" else normalize_unit(input_unit)
        parsed_axis_map = parse_axis_map(axis_map)
        return cls(
            input_unit=resolved_input_unit,
            output_unit=normalize_unit(output_unit),
            mesh_deflection=_resolve_mesh_deflection_input(mesh_deflection),
            angular_deflection=resolve_angular_deflection(angular_deflection),
            axis_map=_format_axis_map(parsed_axis_map),
            step_metric_source=normalize_step_metric_source(step_metric_source),
            step_components=step_components,
            step_component_mode=normalize_step_component_mode(step_component_mode),
            base_tolerance=resolve_base_tolerance(base_tolerance),
            require_mesh=bool(require_mesh),
        )

    @property
    def metric_source_requires_mesh(self) -> bool:
        return self.step_metric_source == "mesh"

    def with_require_mesh(self, require_mesh: bool) -> ModelLoadOptions:
        return replace(self, require_mesh=require_mesh)


def normalize_step_metric_source(value: str) -> StepMetricSource:
    text = value.strip().lower().replace("_", "-")
    if text in {"brep", "b-rep", "exact", "kernel"}:
        return "brep"
    if text in {"mesh", "tessellated", "stl"}:
        return "mesh"
    raise ValueError("step_metric_source must be 'brep' or 'mesh'")


def normalize_step_component_mode(value: str) -> StepComponentMode:
    text = value.strip().lower().replace("_", "-")
    if text in {"filter", "exclude", "hide"}:
        return "filter"
    if text in {"subtract", "cut", "difference"}:
        return "subtract"
    raise ValueError("step_component_mode must be 'filter' or 'subtract'")


def resolve_base_tolerance(value: float) -> float:
    try:
        tolerance = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("base_tolerance must be a number") from exc
    if not isfinite(tolerance):
        raise ValueError("base_tolerance must be finite")
    if tolerance <= 0.0:
        raise ValueError("base_tolerance must be greater than zero")
    return tolerance


def resolve_angular_deflection(value: float) -> float:
    try:
        deflection = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("angular_deflection must be a number") from exc
    if not isfinite(deflection):
        raise ValueError("angular_deflection must be finite")
    if deflection < 0.0:
        raise ValueError("angular_deflection must not be negative")
    return deflection


def _resolve_mesh_deflection_input(value: float | str) -> float | str:
    if isinstance(value, str) and value.strip().lower() == "auto":
        return "auto"
    try:
        deflection = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("mesh_deflection must be a number or 'auto'") from exc
    if not isfinite(deflection):
        raise ValueError("mesh_deflection must be finite")
    if deflection <= 0.0:
        raise ValueError("mesh_deflection must be greater than zero")
    return deflection


def _format_axis_map(axis_map: tuple[tuple[int, float], ...]) -> str:
    names = ("x", "y", "z")
    return ",".join(
        f"{'-' if sign < 0.0 else ''}{names[source_axis]}" for source_axis, sign in axis_map
    )
