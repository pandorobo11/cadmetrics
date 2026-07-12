from __future__ import annotations

from collections.abc import Iterator
from itertools import product
from math import isfinite

from cadmetrics.orientation import Orientation

MAX_SWEEP_COMBINATIONS = 10_000


def parse_sweep_values(spec: str | int | float) -> list[float]:
    if isinstance(spec, int | float):
        value = float(spec)
        _require_finite(value, "Sweep value")
        return [value]

    text = str(spec).strip()
    if not text:
        raise ValueError("Sweep specification cannot be empty")

    if ":" not in text:
        value = float(text)
        _require_finite(value, "Sweep value")
        return [value]

    parts = text.split(":")
    if len(parts) != 3:
        raise ValueError("Sweep range must be start:end:step")

    start, end, step = (float(part) for part in parts)
    _require_finite(start, "Sweep start")
    _require_finite(end, "Sweep end")
    _require_finite(step, "Sweep step")
    if step == 0.0:
        raise ValueError("Sweep step must not be zero")
    if end > start and step < 0.0:
        raise ValueError("Sweep step must be positive when end is greater than start")
    if end < start and step > 0.0:
        raise ValueError("Sweep step must be negative when end is less than start")

    values: list[float] = []
    value = start
    epsilon = abs(step) * 1.0e-9
    if step > 0.0:
        while value <= end + epsilon:
            values.append(_clean_float(value))
            value += step
    else:
        while value >= end - epsilon:
            values.append(_clean_float(value))
            value += step
    return values


def iter_orientations(
    *,
    roll: str | int | float = 0.0,
    alpha: str | int | float = 0.0,
    beta: str | int | float = 0.0,
) -> Iterator[Orientation]:
    rolls, alphas, betas = _orientation_axes(roll=roll, alpha=alpha, beta=beta)
    return (
        Orientation(roll_deg=roll_deg, alpha_deg=alpha_deg, beta_deg=beta_deg)
        for roll_deg, alpha_deg, beta_deg in product(rolls, alphas, betas)
    )


def orientation_count(
    *,
    roll: str | int | float = 0.0,
    alpha: str | int | float = 0.0,
    beta: str | int | float = 0.0,
) -> int:
    rolls, alphas, betas = _orientation_axes(roll=roll, alpha=alpha, beta=beta)
    return len(rolls) * len(alphas) * len(betas)


def _orientation_axes(
    *,
    roll: str | int | float,
    alpha: str | int | float,
    beta: str | int | float,
) -> tuple[list[float], list[float], list[float]]:
    rolls = parse_sweep_values(roll)
    alphas = parse_sweep_values(alpha)
    betas = parse_sweep_values(beta)
    count = len(rolls) * len(alphas) * len(betas)
    if count > MAX_SWEEP_COMBINATIONS:
        raise ValueError(
            f"Sweep would generate {count:,} combinations; "
            f"the maximum is {MAX_SWEEP_COMBINATIONS:,}."
        )
    return rolls, alphas, betas


def _require_finite(value: float, label: str) -> None:
    if not isfinite(value):
        raise ValueError(f"{label} must be finite")


def _clean_float(value: float) -> float:
    rounded = round(value, 12)
    if rounded == -0.0:
        return 0.0
    return rounded
