import pytest

from cadmetrics.sweep import MAX_SWEEP_COMBINATIONS, SweepRange, iter_orientations, parse_sweep_values


def test_parse_single_value() -> None:
    assert parse_sweep_values("3") == [3.0]


def test_single_point_sweep_range_ignores_step() -> None:
    sweep_range = SweepRange(3.0, 3.0, 0.0)

    assert sweep_range.spec == "3.0"
    assert sweep_range.count == 1


def test_parse_inclusive_positive_range() -> None:
    assert parse_sweep_values("-1:1:1") == [-1.0, 0.0, 1.0]


def test_parse_inclusive_negative_range() -> None:
    assert parse_sweep_values("1:-1:-1") == [1.0, 0.0, -1.0]


def test_parse_range_uses_indexed_values_without_cumulative_drift() -> None:
    assert parse_sweep_values("0:0.3:0.1") == [0.0, 0.1, 0.2, 0.3]


def test_parse_range_rejects_more_than_maximum_values_before_allocating() -> None:
    with pytest.raises(ValueError, match=f"maximum is {MAX_SWEEP_COMBINATIONS:,}"):
        parse_sweep_values(f"0:{MAX_SWEEP_COMBINATIONS}:1")


def test_parse_range_rejects_step_that_cannot_advance() -> None:
    with pytest.raises(ValueError, match="too small to advance"):
        parse_sweep_values("10000000000000000:10000000000000002:0.1")


def test_parse_range_rejects_non_finite_span() -> None:
    with pytest.raises(ValueError, match=f"maximum is {MAX_SWEEP_COMBINATIONS:,}"):
        parse_sweep_values("-1e308:1e308:1")


def test_iter_orientations_uses_all_combinations() -> None:
    orientations = list(iter_orientations(roll="0:1:1", alpha="-1:1:1", beta="0"))
    assert len(orientations) == 6
    assert orientations[0].roll_deg == 0.0
    assert orientations[-1].roll_deg == 1.0
    assert orientations[-1].alpha_deg == 1.0
    assert orientations[-1].beta_deg == 0.0


@pytest.mark.parametrize("spec", ["nan", "inf", "-inf", "0:1:inf", "nan:1:1"])
def test_parse_sweep_values_rejects_non_finite_values(spec: str) -> None:
    with pytest.raises(ValueError, match="finite"):
        parse_sweep_values(spec)


def test_iter_orientations_rejects_more_than_maximum_combinations() -> None:
    with pytest.raises(ValueError, match=f"maximum is {MAX_SWEEP_COMBINATIONS:,}"):
        iter_orientations(roll="0:100:1", alpha="0:100:1", beta=0)


def test_iter_orientations_accepts_maximum_combinations() -> None:
    orientations = iter_orientations(roll="1:100:1", alpha="1:100:1", beta=0)
    assert sum(1 for _ in orientations) == MAX_SWEEP_COMBINATIONS
