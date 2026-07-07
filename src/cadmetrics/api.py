from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from typing import Callable

from cadmetrics.coordinates import DEFAULT_AXIS_MAP, transform_model_axes
from cadmetrics.io import DEFAULT_BASE_TOLERANCE, load_model
from cadmetrics.orientation import (
    Orientation,
    alpha_beta_from_direction,
    normalize_vector,
    parse_vector,
    projection_direction_for_orientation,
    roll_pitch_from_direction,
)
from cadmetrics.projection import ProjectionMetrics, projected_metrics
from cadmetrics.projection import projection_basis
from cadmetrics.sweep import iter_orientations
from cadmetrics.types import MeasurementRow, ModelData


def inspect_model(
    path: str | Path | Sequence[str | Path],
    *,
    input_unit: str = "auto",
    output_unit: str = "m",
    mesh_deflection: float | str = "auto",
    angular_deflection: float = 0.1,
    axis_map: str = DEFAULT_AXIS_MAP,
    step_metric_source: str = "brep",
    step_components: tuple[int, ...] | None = None,
    base_tolerance: float = DEFAULT_BASE_TOLERANCE,
    require_mesh: bool = True,
) -> ModelData:
    model = load_model(
        path,
        input_unit=input_unit,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
        step_metric_source=step_metric_source,
        step_components=step_components,
        base_axis_map=axis_map,
        base_tolerance=base_tolerance,
        require_mesh=require_mesh,
    )
    return transform_model_axes(model, axis_map)


def measure(
    path: str | Path | Sequence[str | Path],
    *,
    input_unit: str = "auto",
    output_unit: str = "m",
    mesh_deflection: float | str = "auto",
    angular_deflection: float = 0.1,
    axis_map: str = DEFAULT_AXIS_MAP,
    step_metric_source: str = "brep",
    step_components: tuple[int, ...] | None = None,
    base_tolerance: float = DEFAULT_BASE_TOLERANCE,
) -> MeasurementRow:
    start = perf_counter()
    model = inspect_model(
        path,
        input_unit=input_unit,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
        axis_map=axis_map,
        step_metric_source=step_metric_source,
        step_components=step_components,
        base_tolerance=base_tolerance,
        require_mesh=_step_metric_source_requires_mesh(step_metric_source),
    )
    return measure_model(model, elapsed_sec=perf_counter() - start)


def measure_model(model: ModelData, *, elapsed_sec: float | None = None) -> MeasurementRow:
    return MeasurementRow(
        file=str(model.path),
        input_unit=model.input_unit,
        output_unit=model.output_unit,
        roll_deg=None,
        alpha_deg=None,
        beta_deg=None,
        pitch_deg=None,
        volume=model.volume,
        surface_area=model.surface_area,
        base_area=model.base_area,
        projected_area=None,
        is_watertight=model.is_watertight,
        x_min=model.x_min,
        x_max=model.x_max,
        y_min=model.y_min,
        y_max=model.y_max,
        z_min=model.z_min,
        z_max=model.z_max,
        step_components=model.selected_components,
        step_component_names=_selected_component_names(model),
        mesh_deflection=model.mesh_deflection,
        angular_deflection=model.angular_deflection,
        base_tolerance=model.base_tolerance,
        method=_method_name(model, projected=False),
        elapsed_sec=elapsed_sec,
        cadmetrics_version=model.cadmetrics_version,
        cadmetrics_hash=model.cadmetrics_hash,
        warnings=model.warnings,
    )


def project(
    path: str | Path | Sequence[str | Path],
    *,
    roll_deg: float = 0.0,
    alpha_deg: float = 0.0,
    beta_deg: float = 0.0,
    direction: str | None = None,
    input_unit: str = "auto",
    output_unit: str = "m",
    mesh_deflection: float | str = "auto",
    angular_deflection: float = 0.1,
    axis_map: str = DEFAULT_AXIS_MAP,
    step_metric_source: str = "brep",
    step_components: tuple[int, ...] | None = None,
    base_tolerance: float = DEFAULT_BASE_TOLERANCE,
) -> MeasurementRow:
    start = perf_counter()
    model = inspect_model(
        path,
        input_unit=input_unit,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
        axis_map=axis_map,
        step_metric_source=step_metric_source,
        step_components=step_components,
        base_tolerance=base_tolerance,
    )
    return project_model(
        model,
        roll_deg=roll_deg,
        alpha_deg=alpha_deg,
        beta_deg=beta_deg,
        direction=direction,
        elapsed_sec=perf_counter() - start,
    )


def project_model(
    model: ModelData,
    *,
    roll_deg: float = 0.0,
    alpha_deg: float = 0.0,
    beta_deg: float = 0.0,
    direction: str | None = None,
    elapsed_sec: float = 0.0,
) -> MeasurementRow:
    orientation = Orientation(roll_deg=roll_deg, alpha_deg=alpha_deg, beta_deg=beta_deg)
    vector = parse_vector(direction) if direction is not None else None
    projection_direction = (
        vector if vector is not None else projection_direction_for_orientation(orientation)
    )
    metrics = projected_metrics(model, orientation=orientation if vector is None else None, direction=vector)
    return _projected_row(
        model,
        projection_direction=projection_direction,
        volume=model.volume,
        surface_area=model.surface_area,
        projection_metrics=metrics,
        is_watertight=model.is_watertight,
        mesh_deflection=model.mesh_deflection,
        angular_deflection=model.angular_deflection,
        base_tolerance=model.base_tolerance,
        method=_method_name(model, projected=True),
        elapsed_sec=elapsed_sec,
        warnings=model.warnings,
    )


def _projected_row(
    model: ModelData,
    *,
    projection_direction,
    volume: float | None,
    surface_area: float | None,
    projection_metrics: ProjectionMetrics,
    is_watertight: bool | None,
    mesh_deflection: float | None,
    angular_deflection: float | None,
    base_tolerance: float | None,
    method: str,
    elapsed_sec: float,
    warnings: tuple[str, ...],
) -> MeasurementRow:
    projection_direction = normalize_vector(projection_direction)
    alpha_deg, beta_deg = alpha_beta_from_direction(projection_direction)
    roll_deg, pitch_deg = roll_pitch_from_direction(projection_direction)
    centroid_x, centroid_y, centroid_z = _centroid_model_coordinates(
        model,
        projection_direction=projection_direction,
        centroid_u=projection_metrics.centroid_u,
        centroid_v=projection_metrics.centroid_v,
    )
    return MeasurementRow(
        file=str(model.path),
        input_unit=model.input_unit,
        output_unit=model.output_unit,
        roll_deg=roll_deg,
        alpha_deg=alpha_deg,
        beta_deg=beta_deg,
        pitch_deg=pitch_deg,
        volume=volume,
        surface_area=surface_area,
        base_area=model.base_area,
        projected_area=projection_metrics.area,
        is_watertight=is_watertight,
        direction_x=float(projection_direction[0]),
        direction_y=float(projection_direction[1]),
        direction_z=float(projection_direction[2]),
        centroid_u=projection_metrics.centroid_u,
        centroid_v=projection_metrics.centroid_v,
        centroid_x=centroid_x,
        centroid_y=centroid_y,
        centroid_z=centroid_z,
        x_min=model.x_min,
        x_max=model.x_max,
        y_min=model.y_min,
        y_max=model.y_max,
        z_min=model.z_min,
        z_max=model.z_max,
        step_components=model.selected_components,
        step_component_names=_selected_component_names(model),
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
        base_tolerance=base_tolerance,
        method=method,
        elapsed_sec=elapsed_sec,
        cadmetrics_version=model.cadmetrics_version,
        cadmetrics_hash=model.cadmetrics_hash,
        warnings=warnings,
    )


def _centroid_model_coordinates(
    model: ModelData,
    *,
    projection_direction,
    centroid_u: float | None,
    centroid_v: float | None,
) -> tuple[float | None, float | None, float | None]:
    if centroid_u is None or centroid_v is None:
        return None, None, None
    basis_u, basis_v = projection_basis(projection_direction)
    normal = normalize_vector(projection_direction)
    plane_offset = float(model.vertices.mean(axis=0) @ normal)
    point = basis_u * centroid_u + basis_v * centroid_v + normal * plane_offset
    return float(point[0]), float(point[1]), float(point[2])


def sweep(
    path: str | Path | Sequence[str | Path],
    *,
    roll: str | int | float = 0.0,
    alpha: str | int | float = 0.0,
    beta: str | int | float = 0.0,
    input_unit: str = "auto",
    output_unit: str = "m",
    mesh_deflection: float | str = "auto",
    angular_deflection: float = 0.1,
    progress_callback: Callable[[int, int, Orientation], None] | None = None,
    axis_map: str = DEFAULT_AXIS_MAP,
    step_metric_source: str = "brep",
    step_components: tuple[int, ...] | None = None,
    base_tolerance: float = DEFAULT_BASE_TOLERANCE,
) -> list[MeasurementRow]:
    model = inspect_model(
        path,
        input_unit=input_unit,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
        axis_map=axis_map,
        step_metric_source=step_metric_source,
        step_components=step_components,
        base_tolerance=base_tolerance,
    )
    return sweep_model(
        model,
        roll=roll,
        alpha=alpha,
        beta=beta,
        progress_callback=progress_callback,
    )


def sweep_model(
    model: ModelData,
    *,
    roll: str | int | float = 0.0,
    alpha: str | int | float = 0.0,
    beta: str | int | float = 0.0,
    progress_callback: Callable[[int, int, Orientation], None] | None = None,
) -> list[MeasurementRow]:
    rows: list[MeasurementRow] = []
    orientations = iter_orientations(roll=roll, alpha=alpha, beta=beta)
    total = len(orientations)
    for index, orientation in enumerate(orientations, start=1):
        row_start = perf_counter()
        projection_direction = projection_direction_for_orientation(orientation)
        rows.append(
            _projected_row(
                model,
                projection_direction=projection_direction,
                volume=model.volume,
                surface_area=model.surface_area,
                projection_metrics=projected_metrics(model, orientation=orientation),
                is_watertight=model.is_watertight,
                mesh_deflection=model.mesh_deflection,
                angular_deflection=model.angular_deflection,
                base_tolerance=model.base_tolerance,
                method=_method_name(model, projected=True),
                elapsed_sec=perf_counter() - row_start,
                warnings=model.warnings,
            )
        )
        if progress_callback is not None:
            progress_callback(index, total, orientation)
    return rows


def _selected_component_names(model: ModelData) -> tuple[str, ...]:
    return tuple(
        model.component_names[index - 1]
        for index in model.selected_components
        if 1 <= index <= len(model.component_names)
    )


def _method_name(model: ModelData, *, projected: bool) -> str:
    if model.source_format == "step":
        assembly = "-assembly" if model.is_assembly else ""
        if model.step_metric_source == "mesh":
            base = f"step-mesh{assembly}"
        else:
            base = f"step-brep{assembly}"
        return f"{base}+mesh-projection" if projected else base
    base = "stl-mesh-assembly" if model.is_assembly else "stl-mesh"
    return f"{base}-projection" if projected else base


def _step_metric_source_requires_mesh(value: str) -> bool:
    text = value.strip().lower().replace("_", "-")
    return text in {"mesh", "tessellated", "stl"}
