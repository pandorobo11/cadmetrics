from __future__ import annotations

from pathlib import Path

from cadmetrics.io import load_model
from cadmetrics.orientation import Orientation, parse_vector
from cadmetrics.projection import projected_area
from cadmetrics.sweep import iter_orientations
from cadmetrics.types import MeasurementRow, ModelData


def inspect_model(
    path: str | Path,
    *,
    input_unit: str = "m",
    output_unit: str = "m",
    mesh_deflection: float = 1.0e-3,
    angular_deflection: float = 0.1,
) -> ModelData:
    return load_model(
        path,
        input_unit=input_unit,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
    )


def measure(
    path: str | Path,
    *,
    input_unit: str = "m",
    output_unit: str = "m",
    mesh_deflection: float = 1.0e-3,
    angular_deflection: float = 0.1,
) -> MeasurementRow:
    model = inspect_model(
        path,
        input_unit=input_unit,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
    )
    return MeasurementRow(
        file=str(model.path),
        input_unit=model.input_unit,
        output_unit=model.output_unit,
        roll_deg=None,
        alpha_deg=None,
        beta_deg=None,
        volume=model.volume,
        surface_area=model.surface_area,
        projected_area=None,
        is_watertight=model.is_watertight,
        warnings=model.warnings,
    )


def project(
    path: str | Path,
    *,
    roll_deg: float = 0.0,
    alpha_deg: float = 0.0,
    beta_deg: float = 0.0,
    direction: str | None = None,
    input_unit: str = "m",
    output_unit: str = "m",
    mesh_deflection: float = 1.0e-3,
    angular_deflection: float = 0.1,
) -> MeasurementRow:
    model = inspect_model(
        path,
        input_unit=input_unit,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
    )
    orientation = Orientation(roll_deg=roll_deg, alpha_deg=alpha_deg, beta_deg=beta_deg)
    vector = parse_vector(direction) if direction is not None else None
    area = projected_area(model, orientation=orientation if vector is None else None, direction=vector)
    return MeasurementRow(
        file=str(model.path),
        input_unit=model.input_unit,
        output_unit=model.output_unit,
        roll_deg=None if vector is not None else roll_deg,
        alpha_deg=None if vector is not None else alpha_deg,
        beta_deg=None if vector is not None else beta_deg,
        volume=model.volume,
        surface_area=model.surface_area,
        projected_area=area,
        is_watertight=model.is_watertight,
        warnings=model.warnings,
    )


def sweep(
    path: str | Path,
    *,
    roll: str | int | float = 0.0,
    alpha: str | int | float = 0.0,
    beta: str | int | float = 0.0,
    input_unit: str = "m",
    output_unit: str = "m",
    mesh_deflection: float = 1.0e-3,
    angular_deflection: float = 0.1,
) -> list[MeasurementRow]:
    model = inspect_model(
        path,
        input_unit=input_unit,
        output_unit=output_unit,
        mesh_deflection=mesh_deflection,
        angular_deflection=angular_deflection,
    )
    rows: list[MeasurementRow] = []
    for orientation in iter_orientations(roll=roll, alpha=alpha, beta=beta):
        rows.append(
            MeasurementRow(
                file=str(model.path),
                input_unit=model.input_unit,
                output_unit=model.output_unit,
                roll_deg=orientation.roll_deg,
                alpha_deg=orientation.alpha_deg,
                beta_deg=orientation.beta_deg,
                volume=model.volume,
                surface_area=model.surface_area,
                projected_area=projected_area(model, orientation=orientation),
                is_watertight=model.is_watertight,
                warnings=model.warnings,
            )
        )
    return rows
