from __future__ import annotations

from itertools import product

from cadmetrics.orientation import Orientation


def parse_sweep_values(spec: str | int | float) -> list[float]:
    if isinstance(spec, int | float):
        return [float(spec)]

    text = str(spec).strip()
    if not text:
        raise ValueError("Sweep specification cannot be empty")

    if ":" not in text:
        return [float(text)]

    parts = text.split(":")
    if len(parts) != 3:
        raise ValueError("Sweep range must be start:end:step")

    start, end, step = (float(part) for part in parts)
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
) -> list[Orientation]:
    rolls = parse_sweep_values(roll)
    alphas = parse_sweep_values(alpha)
    betas = parse_sweep_values(beta)
    return [
        Orientation(roll_deg=roll_deg, alpha_deg=alpha_deg, beta_deg=beta_deg)
        for roll_deg, alpha_deg, beta_deg in product(rolls, alphas, betas)
    ]


def _clean_float(value: float) -> float:
    rounded = round(value, 12)
    if rounded == -0.0:
        return 0.0
    return rounded
