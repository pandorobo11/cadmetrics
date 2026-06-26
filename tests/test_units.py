import pytest

from cadmetrics.units import area_scale, length_scale, normalize_unit, volume_scale


def test_normalize_unit_aliases() -> None:
    assert normalize_unit("meters") == "m"
    assert normalize_unit("millimeter") == "mm"
    assert normalize_unit("inch") == "in"


def test_length_scale_from_mm_to_m() -> None:
    assert length_scale("mm", "m") == 0.001


def test_area_and_volume_scale() -> None:
    assert area_scale("cm", "m") == 0.0001
    assert volume_scale("cm", "m") == pytest.approx(0.000001)
