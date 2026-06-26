from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin, sqrt

import numpy as np

from cadmetrics.types import FloatArray


@dataclass(frozen=True)
class Orientation:
    roll_deg: float = 0.0
    alpha_deg: float = 0.0
    beta_deg: float = 0.0


def rotation_matrix(orientation: Orientation) -> FloatArray:
    """Return matrix for roll -> alpha -> beta, using row-vector application with R.T."""

    roll = radians(orientation.roll_deg)
    alpha = radians(orientation.alpha_deg)
    beta = radians(orientation.beta_deg)

    rx = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, cos(roll), -sin(roll)],
            [0.0, sin(roll), cos(roll)],
        ],
        dtype=float,
    )
    ry = np.array(
        [
            [cos(alpha), 0.0, sin(alpha)],
            [0.0, 1.0, 0.0],
            [-sin(alpha), 0.0, cos(alpha)],
        ],
        dtype=float,
    )
    rz = np.array(
        [
            [cos(beta), -sin(beta), 0.0],
            [sin(beta), cos(beta), 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    return rz @ ry @ rx


def projection_direction_for_orientation(orientation: Orientation) -> FloatArray:
    """Return the model-space projection direction for the attitude convention."""

    return normalize_vector(rotation_matrix(orientation).T @ np.array([1.0, 0.0, 0.0], dtype=float))


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
    magnitude = sqrt(float(np.dot(vector, vector)))
    if magnitude == 0.0:
        raise ValueError("Vector magnitude must be greater than zero")
    return vector / magnitude
