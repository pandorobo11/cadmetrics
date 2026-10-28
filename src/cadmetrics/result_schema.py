from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import cast

CsvValue = str | float | bool | None
CsvSerializer = Callable[[object], CsvValue]


def _scalar(value: object) -> CsvValue:
    return cast(CsvValue, value)


def _comma_separated(value: object) -> CsvValue:
    return ",".join(str(item) for item in cast(Iterable[object], value))


def _semicolon_separated(value: object) -> CsvValue:
    return "; ".join(cast(Iterable[str], value))


@dataclass(frozen=True, slots=True)
class ResultFieldSpec:
    """Shared CSV and GUI metadata for one measurement-result field."""

    key: str
    description: str
    gui_label: str
    gui_priority: int | None = None
    serializer: CsvSerializer = field(default=_scalar, repr=False, compare=False)

    @property
    def gui_tooltip(self) -> str:
        return f"CSV field: {self.key}"

    def extract_value(self, row: object) -> CsvValue:
        return self.serializer(getattr(row, self.key))


def _spec(
    key: str,
    description: str,
    *,
    label: str | None = None,
    priority: int | None = None,
    serializer: CsvSerializer = _scalar,
) -> ResultFieldSpec:
    return ResultFieldSpec(
        key=key,
        description=description,
        gui_label=label or key.replace("_", " ").title(),
        gui_priority=priority,
        serializer=serializer,
    )


RESULT_FIELD_SPECS = (
    _spec(
        "file",
        "input path, or semicolon-separated paths for multi-file assemblies",
        label="File",
        priority=0,
    ),
    _spec(
        "step_components",
        "selected STEP component indexes, comma-separated; empty for STL or STEP files "
        "without solid component metadata",
        label="Components",
        serializer=_comma_separated,
    ),
    _spec(
        "step_component_names",
        "selected STEP component names, semicolon-separated",
        label="Component names",
        serializer=_semicolon_separated,
    ),
    _spec("input_unit", "unit used when reading the model", label="Input unit"),
    _spec("output_unit", "unit used for output values", label="Output unit"),
    _spec(
        "attitude",
        "attitude input mode (`alpha-beta`, `roll-pitch`, or `vector`); empty without a projection",
        label="Attitude",
    ),
    _spec(
        "roll_deg",
        "roll angle; as requested in `roll-pitch` mode, otherwise recovered from the "
        "projection direction",
        label="Roll (°)",
        priority=3,
    ),
    _spec(
        "pitch_deg",
        "pitch angle; as requested in `roll-pitch` mode, otherwise recovered from the "
        "projection direction",
        label="Pitch (°)",
        priority=4,
    ),
    _spec(
        "alpha_deg",
        "angle of attack; as requested in `alpha-beta` mode, otherwise recovered from the "
        "projection direction",
        label="Alpha (°)",
        priority=1,
    ),
    _spec(
        "beta_deg",
        "sideslip angle; as requested in `alpha-beta` mode, otherwise recovered from the "
        "projection direction",
        label="Beta (°)",
        priority=2,
    ),
    _spec(
        "direction_x",
        "normalized projection-direction X component",
        label="Direction X",
    ),
    _spec(
        "direction_y",
        "normalized projection-direction Y component",
        label="Direction Y",
    ),
    _spec(
        "direction_z",
        "normalized projection-direction Z component",
        label="Direction Z",
    ),
    _spec("x_min", "minimum model X coordinate in `output_unit`", label="X min"),
    _spec("x_max", "maximum model X coordinate in `output_unit`", label="X max"),
    _spec("y_min", "minimum model Y coordinate in `output_unit`", label="Y min"),
    _spec("y_max", "maximum model Y coordinate in `output_unit`", label="Y max"),
    _spec("z_min", "minimum model Z coordinate in `output_unit`", label="Z min"),
    _spec("z_max", "maximum model Z coordinate in `output_unit`", label="Z max"),
    _spec(
        "surface_area",
        "surface area in `output_unit^2`",
        label="Surface area",
        priority=12,
    ),
    _spec(
        "newly_exposed_surface_area",
        "surface area newly exposed and excluded in subtraction mode",
        label="Newly exposed area",
    ),
    _spec(
        "base_area",
        "exterior face area at cadmetrics-coordinate `Xmax` in `output_unit^2`; `0` with a "
        "warning when no face is found",
        label="Base area",
        priority=13,
    ),
    _spec(
        "volume",
        "volume in `output_unit^3`; empty for non-watertight STL and open, invalid, or "
        "surface-only STEP shapes",
        label="Volume",
        priority=11,
    ),
    _spec(
        "projected_area",
        "orthographic projected outline area in `output_unit^2`",
        label="Projected area",
        priority=5,
    ),
    _spec(
        "centroid_u",
        "projected 2D centroid U coordinate in the projection plane",
        label="Centroid U",
        priority=6,
    ),
    _spec(
        "centroid_v",
        "projected 2D centroid V coordinate in the projection plane",
        label="Centroid V",
        priority=7,
    ),
    _spec(
        "centroid_x",
        "corresponding 3D centroid-marker X coordinate",
        label="Centroid X",
        priority=8,
    ),
    _spec(
        "centroid_y",
        "corresponding 3D centroid-marker Y coordinate",
        label="Centroid Y",
        priority=9,
    ),
    _spec(
        "centroid_z",
        "corresponding 3D centroid-marker Z coordinate",
        label="Centroid Z",
        priority=10,
    ),
    _spec("is_watertight", "mesh or STEP topology watertightness when known", label="Watertight"),
    _spec("mesh_deflection", "effective STEP tessellation deflection, if applicable"),
    _spec("angular_deflection", "effective STEP angular deflection, if applicable"),
    _spec("base_tolerance", "relative tolerance used to identify Xmax base faces"),
    _spec("step_component_mode", "`filter` or `subtract` for STEP input"),
    _spec("method", "calculation backend summary"),
    _spec(
        "load_elapsed_sec",
        "model preparation time, including file loading, validation, geometry operations, "
        "metrics, tessellation, and axis conversion",
        label="Load elapsed (s)",
    ),
    _spec(
        "elapsed_sec",
        "calculation time for this result row after the model is prepared",
        label="Elapsed (s)",
    ),
    _spec("cadmetrics_version", "package version used for the calculation"),
    _spec(
        "cadmetrics_hash",
        "git commit hash used for the calculation, with `-dirty` when tracked files differ",
    ),
    _spec(
        "warnings",
        "semicolon-separated warnings",
        serializer=_semicolon_separated,
    ),
)

RESULT_FIELD_BY_KEY: Mapping[str, ResultFieldSpec] = MappingProxyType(
    {spec.key: spec for spec in RESULT_FIELD_SPECS}
)
if len(RESULT_FIELD_BY_KEY) != len(RESULT_FIELD_SPECS):
    raise RuntimeError("Result field keys must be unique.")

GUI_RESULT_FIELD_SPECS = tuple(
    spec
    for _, spec in sorted(
        enumerate(RESULT_FIELD_SPECS),
        key=lambda item: (
            item[1].gui_priority is None,
            item[1].gui_priority if item[1].gui_priority is not None else item[0],
        ),
    )
)


def serialize_result_row(row: object) -> dict[str, CsvValue]:
    return {spec.key: spec.extract_value(row) for spec in RESULT_FIELD_SPECS}


SECTION_FIELD_SPECS = (
    RESULT_FIELD_BY_KEY["file"],
    RESULT_FIELD_BY_KEY["step_components"],
    RESULT_FIELD_BY_KEY["step_component_names"],
    RESULT_FIELD_BY_KEY["input_unit"],
    RESULT_FIELD_BY_KEY["output_unit"],
    _spec(
        "mach",
        "Mach number; 1 cuts planes normal to X, above 1 cuts Mach planes",
        label="Mach",
    ),
    _spec(
        "theta_deg",
        "roll angle of the Mach planes, from +Y toward +Z; empty at Mach 1",
        label="Theta (°)",
        priority=0,
    ),
    _spec(
        "theta_weight",
        "weight of this roll angle in the averaged wave drag; the weights add up to 1",
        label="Theta weight",
    ),
    _spec("station", "1-based number of the cutting plane in its series", label="Station"),
    _spec(
        "x",
        "where the cutting plane crosses the X axis (Y = Z = 0), in `output_unit`",
        label="X",
        priority=1,
    ),
    _spec(
        "area",
        "section area projected onto the YZ plane, in `output_unit^2`",
        label="Area",
        priority=2,
    ),
    _spec(
        "area_slope",
        "dArea/dX by finite differences, in `output_unit`",
        label="dArea/dX",
        priority=3,
    ),
    _spec(
        "sears_haack_area",
        "area of the Sears-Haack body with the same length and volume, in `output_unit^2`",
        label="Sears-Haack area",
        priority=4,
    ),
    _spec(
        "wave_drag_area",
        "linear-theory wave drag D/q of this roll angle's equivalent body, in `output_unit^2`",
        label="Wave drag D/q",
    ),
    _spec(
        "sears_haack_drag_area",
        "D/q of the matching Sears-Haack body, in `output_unit^2`",
        label="Sears-Haack D/q",
    ),
    _spec(
        "mean_wave_drag_area",
        "wave drag D/q averaged over all roll angles, in `output_unit^2`",
        label="Mean D/q",
    ),
    _spec(
        "open_section",
        "true when the plane crosses a hole in the mesh, so the area may be too small",
        label="Open",
    ),
    RESULT_FIELD_BY_KEY["mesh_deflection"],
    RESULT_FIELD_BY_KEY["angular_deflection"],
    RESULT_FIELD_BY_KEY["step_component_mode"],
    RESULT_FIELD_BY_KEY["method"],
    RESULT_FIELD_BY_KEY["cadmetrics_version"],
    RESULT_FIELD_BY_KEY["cadmetrics_hash"],
    RESULT_FIELD_BY_KEY["warnings"],
)

SECTION_FIELD_BY_KEY: Mapping[str, ResultFieldSpec] = MappingProxyType(
    {spec.key: spec for spec in SECTION_FIELD_SPECS}
)
if len(SECTION_FIELD_BY_KEY) != len(SECTION_FIELD_SPECS):
    raise RuntimeError("Section field keys must be unique.")


def serialize_section_row(row: object) -> dict[str, CsvValue]:
    return {spec.key: spec.extract_value(row) for spec in SECTION_FIELD_SPECS}
