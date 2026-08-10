from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import Callable

from cadmetrics.attitude import (
    ATTITUDE_MODES as ATTITUDE_MODES,
    AttitudeMode,
    ResolvedProjectAttitude,
    ResolvedSweepAttitude,
    SweepValue,
    resolve_project_attitude,
    resolve_sweep_attitude,
)
from cadmetrics.coordinates import DEFAULT_AXIS_MAP, transform_model_axes
from cadmetrics.io import _load_model_with_options
from cadmetrics.load_options import (
    DEFAULT_BASE_TOLERANCE,
    ModelLoadOptions,
    StepComponentMode,
)
from cadmetrics.orientation import (
    alpha_beta_from_direction,
    normalize_vector,
    projection_direction_for_orientation,
    roll_pitch_from_direction,
)
from cadmetrics.projection import ProjectionMetrics, projected_metrics
from cadmetrics.projection import projection_basis
from cadmetrics.sweep import iter_orientations, orientation_count
from cadmetrics.types import FloatArray, MeasurementRow, ModelData


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
    step_component_mode: StepComponentMode = "filter",
    base_tolerance: float = DEFAULT_BASE_TOLERANCE,
    require_mesh: bool = True,
) -> ModelData:
    options = ModelLoadOptions.resolve(
        input_unit=input_unit,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
        axis_map=axis_map,
        step_metric_source=step_metric_source,
        step_components=step_components,
        step_component_mode=step_component_mode,
        base_tolerance=base_tolerance,
        require_mesh=require_mesh,
    )
    return _inspect_model_with_options(path, options)


def _inspect_model_with_options(
    path: str | Path | Sequence[str | Path],
    options: ModelLoadOptions,
) -> ModelData:
    start = perf_counter()
    model = _load_model_with_options(path, options)
    transformed = transform_model_axes(model, options.axis_map)
    return replace(transformed, load_elapsed_sec=perf_counter() - start)


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
    step_component_mode: StepComponentMode = "filter",
    base_tolerance: float = DEFAULT_BASE_TOLERANCE,
) -> MeasurementRow:
    options = ModelLoadOptions.resolve(
        input_unit=input_unit,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
        axis_map=axis_map,
        step_metric_source=step_metric_source,
        step_components=step_components,
        step_component_mode=step_component_mode,
        base_tolerance=base_tolerance,
        require_mesh=False,
    )
    options = options.with_require_mesh(options.metric_source_requires_mesh)
    model = _inspect_model_with_options(path, options)
    return measure_model(model)


def measure_model(model: ModelData, *, elapsed_sec: float | None = None) -> MeasurementRow:
    start = perf_counter()
    row = MeasurementRow(
        file=str(model.path),
        input_unit=model.input_unit,
        output_unit=model.output_unit,
        roll_deg=None,
        alpha_deg=None,
        beta_deg=None,
        pitch_deg=None,
        volume=model.volume,
        surface_area=model.surface_area,
        newly_exposed_surface_area=model.newly_exposed_surface_area,
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
        step_component_mode=model.step_component_mode,
        method=_method_name(model, projected=False),
        load_elapsed_sec=model.load_elapsed_sec,
        elapsed_sec=0.0,
        cadmetrics_version=model.cadmetrics_version,
        cadmetrics_hash=model.cadmetrics_hash,
        warnings=model.warnings,
    )
    return replace(
        row,
        elapsed_sec=elapsed_sec if elapsed_sec is not None else perf_counter() - start,
    )


def project(
    path: str | Path | Sequence[str | Path],
    *,
    attitude: AttitudeMode = "alpha-beta",
    roll_deg: float = 0.0,
    pitch_deg: float = 0.0,
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
    step_component_mode: StepComponentMode = "filter",
    base_tolerance: float = DEFAULT_BASE_TOLERANCE,
) -> MeasurementRow:
    resolved_attitude = resolve_project_attitude(
        attitude=attitude,
        roll_deg=roll_deg,
        pitch_deg=pitch_deg,
        alpha_deg=alpha_deg,
        beta_deg=beta_deg,
        direction=direction,
    )
    options = ModelLoadOptions.resolve(
        input_unit=input_unit,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
        axis_map=axis_map,
        step_metric_source=step_metric_source,
        step_components=step_components,
        step_component_mode=step_component_mode,
        base_tolerance=base_tolerance,
    )
    model = _inspect_model_with_options(path, options)
    return _project_model_with_attitude(model, resolved_attitude)


def project_model(
    model: ModelData,
    *,
    attitude: AttitudeMode = "alpha-beta",
    roll_deg: float = 0.0,
    pitch_deg: float = 0.0,
    alpha_deg: float = 0.0,
    beta_deg: float = 0.0,
    direction: str | None = None,
    elapsed_sec: float | None = None,
) -> MeasurementRow:
    resolved_attitude = resolve_project_attitude(
        attitude=attitude,
        roll_deg=roll_deg,
        pitch_deg=pitch_deg,
        alpha_deg=alpha_deg,
        beta_deg=beta_deg,
        direction=direction,
    )
    return _project_model_with_attitude(model, resolved_attitude, elapsed_sec=elapsed_sec)


def _project_model_with_attitude(
    model: ModelData,
    resolved_attitude: ResolvedProjectAttitude,
    *,
    elapsed_sec: float | None = None,
) -> MeasurementRow:
    start = perf_counter()
    orientation = resolved_attitude.orientation
    vector = resolved_attitude.direction
    if vector is not None:
        projection_direction = vector
    else:
        assert orientation is not None
        projection_direction = projection_direction_for_orientation(orientation)
    metrics = projected_metrics(
        model,
        orientation=orientation if vector is None else None,
        direction=vector,
    )
    row = _projected_row(
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
        elapsed_sec=elapsed_sec if elapsed_sec is not None else 0.0,
        warnings=model.warnings,
    )
    if elapsed_sec is not None:
        return row
    return replace(row, elapsed_sec=perf_counter() - start)


def _projected_row(
    model: ModelData,
    *,
    projection_direction: FloatArray,
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
        newly_exposed_surface_area=model.newly_exposed_surface_area,
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
        step_component_mode=model.step_component_mode,
        method=method,
        load_elapsed_sec=model.load_elapsed_sec,
        elapsed_sec=elapsed_sec,
        cadmetrics_version=model.cadmetrics_version,
        cadmetrics_hash=model.cadmetrics_hash,
        warnings=warnings,
    )


def _centroid_model_coordinates(
    model: ModelData,
    *,
    projection_direction: FloatArray,
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
    attitude: AttitudeMode = "alpha-beta",
    roll_deg: SweepValue = 0.0,
    pitch_deg: SweepValue = 0.0,
    alpha_deg: SweepValue = 0.0,
    beta_deg: SweepValue = 0.0,
    direction: str | None = None,
    input_unit: str = "auto",
    output_unit: str = "m",
    mesh_deflection: float | str = "auto",
    angular_deflection: float = 0.1,
    progress_callback: Callable[[int, int, MeasurementRow], None] | None = None,
    axis_map: str = DEFAULT_AXIS_MAP,
    step_metric_source: str = "brep",
    step_components: tuple[int, ...] | None = None,
    step_component_mode: StepComponentMode = "filter",
    base_tolerance: float = DEFAULT_BASE_TOLERANCE,
) -> list[MeasurementRow]:
    resolved_attitude = resolve_sweep_attitude(
        attitude=attitude,
        roll_deg=roll_deg,
        pitch_deg=pitch_deg,
        alpha_deg=alpha_deg,
        beta_deg=beta_deg,
        direction=direction,
    )
    options = ModelLoadOptions.resolve(
        input_unit=input_unit,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
        axis_map=axis_map,
        step_metric_source=step_metric_source,
        step_components=step_components,
        step_component_mode=step_component_mode,
        base_tolerance=base_tolerance,
    )
    model = _inspect_model_with_options(path, options)
    return _sweep_model_with_attitude(
        model,
        resolved_attitude,
        progress_callback=progress_callback,
    )


def sweep_model(
    model: ModelData,
    *,
    attitude: AttitudeMode = "alpha-beta",
    roll_deg: SweepValue = 0.0,
    pitch_deg: SweepValue = 0.0,
    alpha_deg: SweepValue = 0.0,
    beta_deg: SweepValue = 0.0,
    direction: str | None = None,
    progress_callback: Callable[[int, int, MeasurementRow], None] | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> list[MeasurementRow]:
    resolved_attitude = resolve_sweep_attitude(
        attitude=attitude,
        roll_deg=roll_deg,
        pitch_deg=pitch_deg,
        alpha_deg=alpha_deg,
        beta_deg=beta_deg,
        direction=direction,
    )
    return _sweep_model_with_attitude(
        model,
        resolved_attitude,
        progress_callback=progress_callback,
        cancel_callback=cancel_callback,
    )


def _sweep_model_with_attitude(
    model: ModelData,
    resolved_attitude: ResolvedSweepAttitude,
    *,
    progress_callback: Callable[[int, int, MeasurementRow], None] | None = None,
    cancel_callback: Callable[[], None] | None = None,
) -> list[MeasurementRow]:
    if resolved_attitude.mode == "vector":
        if cancel_callback is not None:
            cancel_callback()
        assert resolved_attitude.direction is not None
        projected_attitude = resolve_project_attitude(
            attitude="vector",
            direction=resolved_attitude.direction,
        )
        row = _project_model_with_attitude(model, projected_attitude)
        if cancel_callback is not None:
            cancel_callback()
        if progress_callback is not None:
            progress_callback(1, 1, row)
        return [row]

    rows: list[MeasurementRow] = []
    total = orientation_count(
        roll=resolved_attitude.roll,
        alpha=resolved_attitude.alpha,
        beta=resolved_attitude.beta,
    )
    orientations = iter_orientations(
        roll=resolved_attitude.roll,
        alpha=resolved_attitude.alpha,
        beta=resolved_attitude.beta,
    )
    for index, orientation in enumerate(orientations, start=1):
        if cancel_callback is not None:
            cancel_callback()
        row_start = perf_counter()
        projection_direction = projection_direction_for_orientation(orientation)
        row = _projected_row(
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
            elapsed_sec=0.0,
            warnings=model.warnings,
        )
        row = replace(row, elapsed_sec=perf_counter() - row_start)
        if cancel_callback is not None:
            cancel_callback()
        rows.append(row)
        if progress_callback is not None:
            progress_callback(index, total, row)
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
        component_mode = "-subtract" if model.step_component_mode == "subtract" else ""
        if model.step_metric_source == "mesh":
            base = f"step-mesh{component_mode}{assembly}"
        else:
            base = f"step-brep{component_mode}{assembly}"
        return f"{base}+mesh-projection" if projected else base
    base = "stl-mesh-assembly" if model.is_assembly else "stl-mesh"
    return f"{base}-projection" if projected else base
