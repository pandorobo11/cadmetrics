from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from cadmetrics.orientation import Orientation, parse_vector
from cadmetrics.sweep import orientation_count, parse_sweep_values
from cadmetrics.types import FloatArray


AttitudeMode = Literal["alpha-beta", "roll-pitch", "vector"]
SweepValue = str | int | float
ATTITUDE_MODES: tuple[AttitudeMode, ...] = ("alpha-beta", "roll-pitch", "vector")


class AttitudeInputError(ValueError):
    """An option is incompatible with the selected attitude representation."""

    def __init__(self, option: str, mode: AttitudeMode, *, required: bool = False) -> None:
        self.option = option
        self.mode = mode
        self.required = required
        action = "is required with" if required else "cannot be used with"
        super().__init__(f"{option} {action} attitude {mode!r}")


@dataclass(frozen=True)
class ResolvedProjectAttitude:
    mode: AttitudeMode
    orientation: Orientation | None
    direction: FloatArray | None


@dataclass(frozen=True)
class ResolvedSweepAttitude:
    mode: AttitudeMode
    roll: SweepValue
    alpha: SweepValue
    beta: SweepValue
    direction: str | None


def normalize_attitude(value: str) -> AttitudeMode:
    mode = value.strip().lower().replace("_", "-")
    if mode not in ATTITUDE_MODES:
        raise ValueError(f"attitude must be one of: {', '.join(ATTITUDE_MODES)}")
    return mode


def resolve_project_attitude(
    *,
    attitude: str,
    roll_deg: float = 0.0,
    pitch_deg: float = 0.0,
    alpha_deg: float = 0.0,
    beta_deg: float = 0.0,
    direction: str | None = None,
) -> ResolvedProjectAttitude:
    mode = normalize_attitude(attitude)
    if mode == "vector":
        _require_direction(direction, mode)
        _reject_nonzero(roll_deg, "roll_deg", mode)
        _reject_nonzero(pitch_deg, "pitch_deg", mode)
        _reject_nonzero(alpha_deg, "alpha_deg", mode)
        _reject_nonzero(beta_deg, "beta_deg", mode)
        assert direction is not None
        return ResolvedProjectAttitude(mode, None, parse_vector(direction))

    if direction is not None:
        raise AttitudeInputError("direction", mode)
    if mode == "roll-pitch":
        _reject_nonzero(alpha_deg, "alpha_deg", mode)
        _reject_nonzero(beta_deg, "beta_deg", mode)
        return ResolvedProjectAttitude(
            mode,
            Orientation(
                roll_deg=_finite_angle(roll_deg, "roll_deg"),
                alpha_deg=_finite_angle(pitch_deg, "pitch_deg"),
            ),
            None,
        )

    _reject_nonzero(roll_deg, "roll_deg", mode)
    _reject_nonzero(pitch_deg, "pitch_deg", mode)
    return ResolvedProjectAttitude(
        mode,
        Orientation(
            alpha_deg=_finite_angle(alpha_deg, "alpha_deg"),
            beta_deg=_finite_angle(beta_deg, "beta_deg"),
        ),
        None,
    )


def resolve_sweep_attitude(
    *,
    attitude: str,
    roll_deg: SweepValue = 0.0,
    pitch_deg: SweepValue = 0.0,
    alpha_deg: SweepValue = 0.0,
    beta_deg: SweepValue = 0.0,
    direction: str | None = None,
) -> ResolvedSweepAttitude:
    mode = normalize_attitude(attitude)
    if mode == "vector":
        _require_direction(direction, mode)
        _reject_nondefault_sweep(roll_deg, "roll_deg", mode)
        _reject_nondefault_sweep(pitch_deg, "pitch_deg", mode)
        _reject_nondefault_sweep(alpha_deg, "alpha_deg", mode)
        _reject_nondefault_sweep(beta_deg, "beta_deg", mode)
        assert direction is not None
        parse_vector(direction)
        return ResolvedSweepAttitude(mode, 0.0, 0.0, 0.0, direction)

    if direction is not None:
        raise AttitudeInputError("direction", mode)
    if mode == "roll-pitch":
        _reject_nondefault_sweep(alpha_deg, "alpha_deg", mode)
        _reject_nondefault_sweep(beta_deg, "beta_deg", mode)
        orientation_count(roll=roll_deg, alpha=pitch_deg, beta=0.0)
        return ResolvedSweepAttitude(mode, roll_deg, pitch_deg, 0.0, None)

    _reject_nondefault_sweep(roll_deg, "roll_deg", mode)
    _reject_nondefault_sweep(pitch_deg, "pitch_deg", mode)
    orientation_count(roll=0.0, alpha=alpha_deg, beta=beta_deg)
    return ResolvedSweepAttitude(mode, 0.0, alpha_deg, beta_deg, None)


def _require_direction(direction: str | None, mode: AttitudeMode) -> None:
    if direction is None:
        raise AttitudeInputError("direction", mode, required=True)


def _reject_nonzero(value: float, option: str, mode: AttitudeMode) -> None:
    if value != 0.0:
        raise AttitudeInputError(option, mode)


def _finite_angle(value: float, option: str) -> float:
    try:
        angle = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{option} must be a number") from exc
    if not isfinite(angle):
        raise ValueError(f"{option} must be finite")
    return angle


def _reject_nondefault_sweep(value: SweepValue, option: str, mode: AttitudeMode) -> None:
    if parse_sweep_values(value) != [0.0]:
        raise AttitudeInputError(option, mode)
