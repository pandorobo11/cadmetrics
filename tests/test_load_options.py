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
