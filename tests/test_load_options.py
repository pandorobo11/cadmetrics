import pytest

from cadmetrics.load_options import ModelLoadOptions


def test_model_load_options_normalize_once() -> None:
    options = ModelLoadOptions.resolve(
        input_unit="MM",
        output_unit="CM",
        mesh_deflection="0.25",
        axis_map="X, -Z, Y",
        step_metric_source="tessellated",
        step_component_mode="difference",
    )

    assert options.input_unit == "mm"
    assert options.output_unit == "cm"
    assert options.mesh_deflection == 0.25
    assert options.axis_map == "x,-z,y"
    assert options.step_metric_source == "mesh"
    assert options.step_component_mode == "subtract"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"mesh_deflection": 0.0}, "mesh_deflection must be greater than zero"),
        ({"base_tolerance": 0.0}, "base_tolerance must be greater than zero"),
        ({"angular_deflection": -1.0}, "angular_deflection must not be negative"),
        ({"step_metric_source": "unknown"}, "step_metric_source must be"),
    ],
)
def test_model_load_options_reject_invalid_values(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ModelLoadOptions.resolve(**kwargs)


@pytest.mark.parametrize(
    ("mesh_deflection", "angular_deflection", "expected_mesh", "expected_angular"),
    [
        ("auto", "auto", "auto", 0.1),
        ("AUTO-FAST", "auto", "auto-fast", 0.3),
        ("auto_fast", "Auto", "auto-fast", 0.3),
        ("auto-fast", 0.05, "auto-fast", 0.05),
        ("auto-fast", "0.4", "auto-fast", 0.4),
        (0.01, "auto", 0.01, 0.1),
    ],
)
def test_angular_deflection_auto_follows_mesh_preset(
    mesh_deflection: object,
    angular_deflection: object,
    expected_mesh: object,
    expected_angular: float,
) -> None:
    options = ModelLoadOptions.resolve(
        mesh_deflection=mesh_deflection,  # type: ignore[arg-type]
        angular_deflection=angular_deflection,  # type: ignore[arg-type]
    )

    assert options.mesh_deflection == expected_mesh
    assert options.angular_deflection == pytest.approx(expected_angular)


def test_default_options_keep_accurate_auto_preset() -> None:
    options = ModelLoadOptions.resolve()

    assert options.mesh_deflection == "auto"
    assert options.angular_deflection == 0.1
    assert ModelLoadOptions().angular_deflection == 0.1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"mesh_deflection": "fast"}, "mesh_deflection must be a number, 'auto', or 'auto-fast'"),
        ({"angular_deflection": "coarse"}, "angular_deflection must be a number or 'auto'"),
    ],
)
def test_mesh_presets_reject_unknown_names(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ModelLoadOptions.resolve(**kwargs)  # type: ignore[arg-type]
