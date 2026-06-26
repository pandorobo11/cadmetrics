from cadmetrics.sweep import iter_orientations, parse_sweep_values


def test_parse_single_value() -> None:
    assert parse_sweep_values("3") == [3.0]


def test_parse_inclusive_positive_range() -> None:
    assert parse_sweep_values("-1:1:1") == [-1.0, 0.0, 1.0]


def test_parse_inclusive_negative_range() -> None:
    assert parse_sweep_values("1:-1:-1") == [1.0, 0.0, -1.0]


def test_iter_orientations_uses_all_combinations() -> None:
    orientations = iter_orientations(roll="0:1:1", alpha="-1:1:1", beta="0")
    assert len(orientations) == 6
    assert orientations[0].roll_deg == 0.0
    assert orientations[-1].roll_deg == 1.0
    assert orientations[-1].alpha_deg == 1.0
    assert orientations[-1].beta_deg == 0.0
