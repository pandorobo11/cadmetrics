from __future__ import annotations

LENGTH_TO_METERS = {
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "mm": 1.0e-3,
    "millimeter": 1.0e-3,
    "millimeters": 1.0e-3,
    "cm": 1.0e-2,
    "centimeter": 1.0e-2,
    "centimeters": 1.0e-2,
    "in": 0.0254,
    "inch": 0.0254,
    "inches": 0.0254,
    "ft": 0.3048,
    "foot": 0.3048,
    "feet": 0.3048,
}


def normalize_unit(unit: str) -> str:
    normalized = unit.strip().lower()
    if normalized not in LENGTH_TO_METERS:
        supported = ", ".join(sorted({"m", "mm", "cm", "in", "ft"}))
        raise ValueError(f"Unsupported unit '{unit}'. Supported units: {supported}")
    aliases = {
        "meter": "m",
        "meters": "m",
        "millimeter": "mm",
        "millimeters": "mm",
        "centimeter": "cm",
        "centimeters": "cm",
        "inch": "in",
        "inches": "in",
        "foot": "ft",
        "feet": "ft",
    }
    return aliases.get(normalized, normalized)


def length_scale(input_unit: str, output_unit: str) -> float:
    source = LENGTH_TO_METERS[normalize_unit(input_unit)]
    target = LENGTH_TO_METERS[normalize_unit(output_unit)]
    return source / target


def area_scale(input_unit: str, output_unit: str) -> float:
    scale = length_scale(input_unit, output_unit)
    return scale * scale


def volume_scale(input_unit: str, output_unit: str) -> float:
    scale = length_scale(input_unit, output_unit)
    return scale * scale * scale
