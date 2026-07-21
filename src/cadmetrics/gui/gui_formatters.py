from __future__ import annotations

from pathlib import Path

from cadmetrics.gui.jobs import CalculationRequest
from cadmetrics.types import MeasurementRow, ModelData


def format_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)


def format_file_selection(paths: tuple[Path, ...]) -> str:
    if not paths:
        return ""
    if len(paths) == 1:
        return str(paths[0])
    return f"{paths[0].name} + {len(paths) - 1} more"


def format_model_file_label(path: Path) -> str:
    parts = [part.strip() for part in str(path).split(";") if part.strip()]
    if len(parts) <= 1:
        return path.name
    names = [Path(part).name for part in parts]
    if len(names) <= 3:
        return " + ".join(names)
    return f"{names[0]} + {len(names) - 1} more"


def component_display_groups(
    component_names: tuple[str, ...],
    *,
    grouped: bool,
) -> list[tuple[str | None, list[tuple[int, str]]]]:
    if not grouped:
        return [(None, list(enumerate(component_names, start=1)))]
    groups: list[tuple[str | None, list[tuple[int, str]]]] = []
    group_index_by_name: dict[str | None, int] = {}
    for index, full_name in enumerate(component_names, start=1):
        group_name, component_name = (
            full_name.split(": ", 1) if ": " in full_name else (None, full_name)
        )
        if group_name not in group_index_by_name:
            group_index_by_name[group_name] = len(groups)
            groups.append((group_name, []))
        groups[group_index_by_name[group_name]][1].append((index, component_name))
    return groups


def overlay_text(
    row: MeasurementRow | None,
    *,
    model: ModelData | None,
    request: CalculationRequest | None,
) -> str:
    if row is not None:
        lines = [
            "cadmetrics result",
            f"file: {format_model_file_label(Path(row.file))}",
            f"unit: {row.output_unit}",
            f"roll/pitch: {_format_angle(row.roll_deg)}, {_format_angle(row.pitch_deg)} deg",
            f"alpha/beta: {_format_angle(row.alpha_deg)}, {_format_angle(row.beta_deg)} deg",
        ]
        if row.direction_x is not None:
            lines.append(
                "direction: "
                f"({_format_vector(row.direction_x)}, {_format_vector(row.direction_y)}, "
                f"{_format_vector(row.direction_z)})"
            )
        lines.extend(
            [
                "bounds: "
                f"X[{_format_metric(row.x_min)}, {_format_metric(row.x_max)}], "
                f"Y[{_format_metric(row.y_min)}, {_format_metric(row.y_max)}], "
                f"Z[{_format_metric(row.z_min)}, {_format_metric(row.z_max)}]",
                f"surface_area: {_format_metric(row.surface_area)}",
                "newly_exposed_surface_area: "
                f"{_format_metric(row.newly_exposed_surface_area)}",
                f"base_area: {_format_metric(row.base_area)}",
                f"volume: {_format_metric(row.volume)}",
                f"projected_area: {_format_metric(row.projected_area)}",
                "centroid: "
                f"({_format_vector(row.centroid_x)}, {_format_vector(row.centroid_y)}, "
                f"{_format_vector(row.centroid_z)})",
            ]
        )
        if row.method:
            lines.append(f"method: {row.method}")
        if row.step_component_mode:
            lines.append(f"component_mode: {row.step_component_mode}")
        lines.extend(
            [
                f"cadmetrics_version: {row.cadmetrics_version}",
                f"cadmetrics_hash: {row.cadmetrics_hash}",
            ]
        )
        if row.warnings:
            lines.append(f"warnings: {'; '.join(row.warnings)}")
        return "\n".join(lines)

    if model is None and request is None:
        return ""
    lines = ["cadmetrics view"]
    if model is not None:
        lines.extend(
            [
                f"file: {format_model_file_label(model.path)}",
                f"format: {model.source_format}",
                f"unit: {model.output_unit}",
                "bounds: "
                f"X[{_format_metric(model.x_min)}, {_format_metric(model.x_max)}], "
                f"Y[{_format_metric(model.y_min)}, {_format_metric(model.y_max)}], "
                f"Z[{_format_metric(model.z_min)}, {_format_metric(model.z_max)}]",
                f"surface_area: {_format_metric(model.surface_area)}",
                "newly_exposed_surface_area: "
                f"{_format_metric(model.newly_exposed_surface_area)}",
                f"base_area: {_format_metric(model.base_area)}",
                f"volume: {_format_metric(model.volume)}",
                f"cadmetrics_version: {model.cadmetrics_version}",
                f"cadmetrics_hash: {model.cadmetrics_hash}",
            ]
        )
        if model.is_assembly:
            lines.insert(2, "assembly: True")
    if request is not None:
        lines.append(f"input: {request.attitude_mode}")
        if request.attitude_mode == "roll_pitch":
            lines.extend(
                [
                    f"roll: {_format_sweep(request.roll_start, request.roll_end, request.roll_step)} deg",
                    f"pitch: {_format_sweep(request.pitch_start, request.pitch_end, request.pitch_step)} deg",
                ]
            )
        elif request.attitude_mode == "vector":
            lines.append(
                "direction: "
                f"({_format_vector(request.vector_x)}, {_format_vector(request.vector_y)}, "
                f"{_format_vector(request.vector_z)})"
            )
        else:
            lines.extend(
                [
                    f"alpha: {_format_sweep(request.alpha_start, request.alpha_end, request.alpha_step)} deg",
                    f"beta: {_format_sweep(request.beta_start, request.beta_end, request.beta_step)} deg",
                ]
            )
    return "\n".join(lines)


def model_info_text(model: ModelData) -> str:
    lines = [
        f"file: {format_model_file_label(model.path)}",
        f"format: {model.source_format}",
        f"vertices: {model.vertex_count}",
        f"faces: {model.face_count}",
        f"x: [{_format_metric(model.x_min)}, {_format_metric(model.x_max)}]",
        f"y: [{_format_metric(model.y_min)}, {_format_metric(model.y_max)}]",
        f"z: [{_format_metric(model.z_min)}, {_format_metric(model.z_max)}]",
        f"volume: {_format_metric(model.volume)}",
        f"surface_area: {_format_metric(model.surface_area)}",
        f"base_area: {_format_metric(model.base_area)}",
        f"watertight: {model.is_watertight}",
    ]
    if model.component_names:
        lines.insert(3, f"components: {len(model.selected_components)} of {len(model.component_names)} selected")
    if model.step_component_mode:
        lines.append(f"component_mode: {model.step_component_mode}")
    if model.newly_exposed_surface_area is not None:
        lines.append(
            "newly_exposed_surface_area: "
            f"{_format_metric(model.newly_exposed_surface_area)}"
        )
    if model.is_assembly:
        lines.insert(1, "assembly: True")
    if model.warnings:
        lines.append(f"warnings: {'; '.join(model.warnings)}")
    return "\n".join(lines)


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6g}"


def _format_angle(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3g}"


def _format_vector(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4g}"


def _format_sweep(start: float, end: float, step: float) -> str:
    return f"{start:.3g}" if start == end else f"{start:.3g}:{end:.3g}:{step:.3g}"
