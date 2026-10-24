import pytest

from cadmetrics.sweep import (
    MAX_SWEEP_COMBINATIONS,
    SweepRange,
    iter_orientations,
    parse_sweep_values,
)


def test_single_point_sweep_range_ignores_step() -> None:
    sweep_range = SweepRange(3.0, 3.0, 0.0)

    assert sweep_range.spec == "3.0"
    assert sweep_range.count == 1


def test_parse_inclusive_negative_range() -> None:
    assert parse_sweep_values("1:-1:-1") == [1.0, 0.0, -1.0]


def test_parse_range_uses_indexed_values_without_cumulative_drift() -> None:
    assert parse_sweep_values("0:0.3:0.1") == [0.0, 0.1, 0.2, 0.3]


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("90:90.00000000001:0.00000000001", [90.0, 90.00000000001]),
        ("90.00000000001:90:-0.00000000001", [90.00000000001, 90.0]),
    ],
)
def test_parse_range_preserves_near_edge_on_values(spec: str, expected: list[float]) -> None:
    # Direct Orientation tests do not exercise range parsing or its rounding.
    assert parse_sweep_values(spec) == expected


def test_parse_range_rejects_more_than_maximum_values_before_allocating() -> None:
    with pytest.raises(ValueError, match=f"maximum is {MAX_SWEEP_COMBINATIONS:,}"):
        parse_sweep_values(f"0:{MAX_SWEEP_COMBINATIONS}:1")


def test_parse_range_rejects_step_that_cannot_advance() -> None:
    with pytest.raises(ValueError, match="too small to advance"):
        parse_sweep_values("10000000000000000:10000000000000002:0.1")


def test_parse_range_rejects_non_finite_span() -> None:
    with pytest.raises(ValueError, match=f"maximum is {MAX_SWEEP_COMBINATIONS:,}"):
        parse_sweep_values("-1e308:1e308:1")


@pytest.mark.parametrize("spec", ["nan", "0:1:inf", "nan:1:1"])
def test_parse_sweep_values_rejects_non_finite_values(spec: str) -> None:
    with pytest.raises(ValueError, match="finite"):
        parse_sweep_values(spec)


def test_iter_orientations_accepts_maximum_combinations() -> None:
    orientations = iter_orientations(roll="1:100:1", alpha="1:100:1", beta=0)
    assert sum(1 for _ in orientations) == MAX_SWEEP_COMBINATIONS
