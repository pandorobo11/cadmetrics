from __future__ import annotations

import os
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Callable

import numpy as np

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
    Orientation,
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
    angular_deflection: float | str = "auto",
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
    # Display-only component meshes are not part of model preparation.
    elapsed = perf_counter() - start - model.component_mesh_elapsed_sec
    return replace(transformed, load_elapsed_sec=elapsed)


def measure(
    path: str | Path | Sequence[str | Path],
    *,
    input_unit: str = "auto",
    output_unit: str = "m",
    mesh_deflection: float | str = "auto",
    angular_deflection: float | str = "auto",
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
    row = _model_row(model, projected=False)
    return replace(
        row,
        elapsed_sec=elapsed_sec if elapsed_sec is not None else perf_counter() - start,
    )


def _model_row(model: ModelData, *, projected: bool) -> MeasurementRow:
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
        method=_method_name(model, projected=projected),
        load_elapsed_sec=model.load_elapsed_sec,
        elapsed_sec=0.0,
        cadmetrics_version=model.cadmetrics_version,
        cadmetrics_hash=model.cadmetrics_hash,
        warnings=model.warnings,
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
    angular_deflection: float | str = "auto",
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
        projection_metrics=metrics,
        elapsed_sec=elapsed_sec if elapsed_sec is not None else 0.0,
        attitude=resolved_attitude.mode,
        orientation=orientation,
    )
    if elapsed_sec is not None:
        return row
    return replace(row, elapsed_sec=perf_counter() - start)


def _projected_row(
    model: ModelData,
    *,
    projection_direction: FloatArray,
    projection_metrics: ProjectionMetrics,
    elapsed_sec: float,
    attitude: AttitudeMode,
    orientation: Orientation | None = None,
) -> MeasurementRow:
    projection_direction = normalize_vector(projection_direction)
    alpha_deg, beta_deg = alpha_beta_from_direction(projection_direction)
    roll_deg, pitch_deg = roll_pitch_from_direction(projection_direction)
    # The input mode's own pair keeps the requested angles unnormalized, so every
    # sweep point is reported where it was asked for; the other pair is recovered.
    if orientation is not None and attitude == "alpha-beta":
        alpha_deg, beta_deg = orientation.alpha_deg, orientation.beta_deg
    elif orientation is not None and attitude == "roll-pitch":
        # In roll-pitch mode Orientation.alpha_deg carries the pitch angle.
        roll_deg, pitch_deg = orientation.roll_deg, orientation.alpha_deg
    centroid_x, centroid_y, centroid_z = _centroid_model_coordinates(
        model,
        projection_direction=projection_direction,
        centroid_u=projection_metrics.centroid_u,
        centroid_v=projection_metrics.centroid_v,
    )
    return replace(
        _model_row(model, projected=True),
        attitude=attitude,
        roll_deg=roll_deg,
        alpha_deg=alpha_deg,
        beta_deg=beta_deg,
        pitch_deg=pitch_deg,
        projected_area=projection_metrics.area,
        direction_x=float(projection_direction[0]),
        direction_y=float(projection_direction[1]),
        direction_z=float(projection_direction[2]),
        centroid_u=projection_metrics.centroid_u,
        centroid_v=projection_metrics.centroid_v,
        centroid_x=centroid_x,
        centroid_y=centroid_y,
        centroid_z=centroid_z,
        elapsed_sec=elapsed_sec,
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
    angular_deflection: float | str = "auto",
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
    max_workers: int | None = None,
    reuse_directions: bool = True,
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
    return _sweep_orientations(
        model,
        list(orientations),
        attitude=resolved_attitude.mode,
        total=total,
        progress_callback=progress_callback,
        cancel_callback=cancel_callback,
        max_workers=max_workers,
        reuse_directions=reuse_directions,
    )


@dataclass(frozen=True)
class _SweepDirection:
    """A distinct projection direction shared by one or more sweep rows."""

    orientation: Orientation
    direction: FloatArray


def _sweep_orientations(
    model: ModelData,
    orientations: list[Orientation],
    *,
    attitude: AttitudeMode,
    total: int,
    progress_callback: Callable[[int, int, MeasurementRow], None] | None,
    cancel_callback: Callable[[], None] | None,
    max_workers: int | None,
    reuse_directions: bool,
) -> list[MeasurementRow]:
    # Each row maps to a distinct direction; d and -d project onto the same plane,
    # so their outlines are mirror images with equal area and the same 3D centroid.
    row_directions: list[FloatArray] = []
    row_keys: list[int] = []
    distinct: list[_SweepDirection] = []
    key_index: dict[tuple[float, float, float], int] = {}
    for orientation in orientations:
        direction = projection_direction_for_orientation(orientation)
        row_directions.append(direction)
        if reuse_directions:
            direction_key = _direction_key(direction)
            index = key_index.get(direction_key)
            if index is None:
                index = key_index[direction_key] = len(distinct)
                distinct.append(_SweepDirection(orientation, direction))
        else:
            index = len(distinct)
            distinct.append(_SweepDirection(orientation, direction))
        row_keys.append(index)

    def compute(item: _SweepDirection) -> tuple[ProjectionMetrics, float]:
        start = perf_counter()
        metrics = projected_metrics(model, orientation=item.orientation)
        return metrics, perf_counter() - start

    workers = _sweep_worker_count(len(distinct), max_workers)
    executor = ThreadPoolExecutor(max_workers=workers) if workers > 1 else None
    # Keep only a bounded number of directions queued ahead of the row being
    # emitted, so cancellation never leaves a long backlog behind.
    window = workers * 2
    futures: dict[int, Future[tuple[ProjectionMetrics, float]]] = {}
    results: dict[int, ProjectionMetrics] = {}
    next_submit = 0
    rows: list[MeasurementRow] = []
    try:
        for row_number, (orientation, direction, key) in enumerate(
            zip(orientations, row_directions, row_keys, strict=True), 1
        ):
            if cancel_callback is not None:
                cancel_callback()
            row_start = perf_counter()
            compute_elapsed = 0.0
            metrics = results.get(key)
            if metrics is None:
                if executor is None:
                    metrics, compute_elapsed = compute(distinct[key])
                else:
                    while next_submit < len(distinct) and next_submit < key + window:
                        futures[next_submit] = executor.submit(compute, distinct[next_submit])
                        next_submit += 1
                    future = futures.pop(key)
                    while not future.done():
                        wait((future,), timeout=_CANCEL_POLL_SEC)
                        if cancel_callback is not None:
                            cancel_callback()
                    metrics, compute_elapsed = future.result()
                results[key] = metrics
                row_start = perf_counter()
            row_metrics = _metrics_for_direction(metrics, distinct[key].direction, direction)
            row = _projected_row(
                model,
                projection_direction=direction,
                projection_metrics=row_metrics,
                elapsed_sec=0.0,
                attitude=attitude,
                orientation=orientation,
            )
            row = replace(row, elapsed_sec=compute_elapsed + perf_counter() - row_start)
            if cancel_callback is not None:
                cancel_callback()
            rows.append(row)
            if progress_callback is not None:
                progress_callback(row_number, total, row)
    finally:
        if executor is not None:
            # On cancellation, drop queued directions and return without waiting
            # for the ones already inside shapely; their results are discarded.
            executor.shutdown(wait=False, cancel_futures=True)
    return rows


_MAX_SWEEP_WORKERS = 8
_CANCEL_POLL_SEC = 0.05


def _sweep_worker_count(distinct_directions: int, max_workers: int | None) -> int:
    if max_workers is None:
        max_workers = min(os.cpu_count() or 1, _MAX_SWEEP_WORKERS)
    return max(1, min(max_workers, distinct_directions))


def _direction_key(direction: FloatArray) -> tuple[float, float, float]:
    """Return a key shared only by exactly equal or exactly reversed directions."""

    # No rounding: a direction a few ulps away can be the one that turns an edge-on
    # face into a tiny positive area. Equivalent attitudes still share a key because
    # orientation._sin_cos_degrees reduces whole and half turns exactly.
    # Adding 0.0 turns -0.0 into 0.0 so both signs of a zero component match.
    values = [float(value) + 0.0 for value in direction]
    leading = next((value for value in values if value != 0.0), 0.0)
    if leading < 0.0:
        values = [-value + 0.0 for value in values]
    return values[0], values[1], values[2]


def _metrics_for_direction(
    metrics: ProjectionMetrics,
    computed_direction: FloatArray,
    direction: FloatArray,
) -> ProjectionMetrics:
    """Express metrics computed along one direction in another direction's basis."""

    if np.array_equal(computed_direction, direction):
        return metrics
    if metrics.centroid_u is None or metrics.centroid_v is None:
        return metrics
    computed_u, computed_v = projection_basis(computed_direction)
    centroid = computed_u * metrics.centroid_u + computed_v * metrics.centroid_v
    basis_u, basis_v = projection_basis(direction)
    return ProjectionMetrics(
        area=metrics.area,
        centroid_u=float(centroid @ basis_u),
        centroid_v=float(centroid @ basis_v),
    )


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
