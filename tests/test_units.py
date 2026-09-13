import pytest

from cadmetrics.api import inspect_model
from cadmetrics.units import area_scale, normalize_unit, volume_scale


def test_normalize_unit_aliases() -> None:
    assert normalize_unit("meters") == "m"
    assert normalize_unit("millimeter") == "mm"
    assert normalize_unit("inch") == "in"


def test_area_and_volume_scale() -> None:
    assert area_scale("cm", "m") == 0.0001
    assert volume_scale("cm", "m") == pytest.approx(0.000001)


@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("mesh_deflection", float("nan"), "mesh_deflection must be finite"),
        ("angular_deflection", float("inf"), "angular_deflection must be finite"),
        ("base_tolerance", float("nan"), "base_tolerance must be finite"),
    ],
)
def test_model_options_reject_non_finite_values(keyword: str, value: float, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        inspect_model("tests/data/unit_cube.stl", **{keyword: value})
