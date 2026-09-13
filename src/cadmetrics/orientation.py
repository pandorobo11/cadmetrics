from __future__ import annotations

from dataclasses import dataclass
from math import asin, atan2, cos, degrees, isfinite, radians, sin, sqrt

import numpy as np

from cadmetrics.types import FloatArray


@dataclass(frozen=True)
class Orientation:
    roll_deg: float = 0.0
    alpha_deg: float = 0.0
    beta_deg: float = 0.0


def rotation_matrix(orientation: Orientation) -> FloatArray:
    """Return matrix for roll -> alpha -> beta, using row-vector application with R.T."""

    sin_roll, cos_roll = _sin_cos_degrees(orientation.roll_deg)
    sin_alpha, cos_alpha = _sin_cos_degrees(orientation.alpha_deg)
    sin_beta, cos_beta = _sin_cos_degrees(orientation.beta_deg)

    rx = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, cos_roll, sin_roll],
            [0.0, -sin_roll, cos_roll],
        ],
        dtype=float,
    )
    ry = np.array(
        [
            [cos_alpha, 0.0, sin_alpha],
            [0.0, 1.0, 0.0],
            [-sin_alpha, 0.0, cos_alpha],
        ],
        dtype=float,
    )
    rz = np.array(
        [
            [cos_beta, -sin_beta, 0.0],
            [sin_beta, cos_beta, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    return rz @ ry @ rx


def _sin_cos_degrees(angle_deg: float) -> tuple[float, float]:
    # Only exact quarter turns bypass trig roundoff; nearby angles keep their
    # small components, which can represent genuinely positive projected areas.
    if angle_deg % 90.0 == 0.0:
        quadrant = int((angle_deg % 360.0) / 90.0)
        return ((0.0, 1.0), (1.0, 0.0), (0.0, -1.0), (-1.0, 0.0))[quadrant]
    angle = radians(angle_deg)
    return sin(angle), cos(angle)


def projection_direction_for_orientation(orientation: Orientation) -> FloatArray:
    """Return the model-space projection direction for the attitude convention."""

    return normalize_vector(rotation_matrix(orientation).T @ np.array([1.0, 0.0, 0.0], dtype=float))


def alpha_beta_from_direction(direction: FloatArray) -> tuple[float, float]:
    """Return alpha/beta angles for a projection direction with roll fixed to zero."""

    unit = normalize_vector(direction)
    alpha = degrees(atan2(float(unit[2]), float(unit[0])))
    beta = degrees(asin(max(min(-float(unit[1]), 1.0), -1.0)))
    return _clean_zero(alpha), _clean_zero(beta)


def roll_pitch_from_direction(direction: FloatArray) -> tuple[float, float]:
    """Return roll/pitch angles for a projection direction.

    Pitch is the angle away from +X. Roll is the azimuth around +X, measured so
    +Z is roll=0 and -Y is roll=90.
    """

    unit = normalize_vector(direction)
    radial = sqrt(float(unit[1] ** 2 + unit[2] ** 2))
    pitch = degrees(atan2(radial, float(unit[0])))
    roll = 0.0 if radial == 0.0 else degrees(atan2(-float(unit[1]), float(unit[2])))
    return _clean_zero(roll), _clean_zero(pitch)


def parse_vector(value: str) -> FloatArray:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise ValueError("Vector must have exactly three comma-separated values, e.g. 1,0,0")
    try:
        vector = np.array([float(part) for part in parts], dtype=float)
    except ValueError as exc:
        raise ValueError(f"Invalid vector '{value}'") from exc
    return normalize_vector(vector)


def normalize_vector(vector: FloatArray) -> FloatArray:
    if not bool(np.all(np.isfinite(vector))):
        raise ValueError("Vector components must be finite")
    magnitude = sqrt(float(np.dot(vector, vector)))
    if not isfinite(magnitude):
        raise ValueError("Vector magnitude must be finite")
    if magnitude == 0.0:
        raise ValueError("Vector magnitude must be greater than zero")
    return vector / magnitude


def _clean_zero(value: float) -> float:
    return 0.0 if abs(value) < 1.0e-12 else value
