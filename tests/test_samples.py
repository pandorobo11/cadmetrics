from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from cadmetrics.api import measure, project


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = json.loads((ROOT / "samples" / "metadata.json").read_text(encoding="utf-8"))["samples"]
HAS_OCP = importlib.util.find_spec("OCP") is not None


@pytest.mark.parametrize("kind", ["ascii_stl", "binary_stl", "step"])
def test_box_sample_exact_metrics(kind: str) -> None:
    if kind == "step" and not HAS_OCP:
        pytest.skip("STEP sample checks require cadmetrics[step]")
    path = ROOT / SAMPLES["box_1x2x3"]["files"][kind]
    projected = project(path)

    assert projected.volume == pytest.approx(6.0)
    assert projected.surface_area == pytest.approx(22.0)
    assert projected.base_area == pytest.approx(6.0)
    assert projected.projected_area == pytest.approx(6.0)
    assert projected.is_watertight is True


@pytest.mark.parametrize("kind", ["ascii_stl", "step"])
def test_cylinder_sample_xmax_base_area(kind: str) -> None:
    if kind == "step" and not HAS_OCP:
        pytest.skip("STEP sample checks require cadmetrics[step]")
    path = ROOT / SAMPLES["cylinder_x_r1_l2"]["files"][kind]
    measured = measure(path)

    assert measured.base_area == pytest.approx(3.141592653589793, rel=1.0e-3)


@pytest.mark.parametrize("kind", ["ascii_stl", "step"])
def test_sphere_sample_has_no_xmax_base_face(kind: str) -> None:
    if kind == "step" and not HAS_OCP:
        pytest.skip("STEP sample checks require cadmetrics[step]")
    path = ROOT / SAMPLES["sphere_r1"]["files"][kind]
    measured = measure(path)

    assert measured.base_area == pytest.approx(0.0)
    assert "base_area set to 0" in "; ".join(measured.warnings)


def test_intersecting_boxes_stl_keeps_raw_component_measurements() -> None:
    path = ROOT / SAMPLES["two_boxes_intersecting"]["files"]["ascii_stl"]
    expected = SAMPLES["two_boxes_intersecting"]["expected"]
    projected = project(path)

    assert projected.volume == pytest.approx(expected["volume_stl"])
    assert projected.surface_area == pytest.approx(expected["surface_area_stl"])
    assert projected.base_area == pytest.approx(expected["base_area_stl"])
    assert projected.projected_area == pytest.approx(expected["projected_area_x"])
    assert projected.is_watertight is True


@pytest.mark.parametrize("kind", ["ascii_stl", "step"])
def test_frame_sample_preserves_hole_in_z_projection(kind: str) -> None:
    if kind == "step" and not HAS_OCP:
        pytest.skip("STEP sample checks require cadmetrics[step]")
    path = ROOT / SAMPLES["frame_with_hole"]["files"][kind]
    projected = project(path, attitude="vector", direction="0,0,1")

    assert projected.volume == pytest.approx(0.8)
    assert projected.surface_area == pytest.approx(17.6)
    assert projected.base_area == pytest.approx(0.3)
    assert projected.projected_area == pytest.approx(8.0)
    assert projected.is_watertight is True


def test_open_cube_sample_warns_about_non_watertight_mesh() -> None:
    path = ROOT / SAMPLES["open_cube_missing_face"]["files"]["ascii_stl"]
    measured = measure(path)

    assert measured.surface_area == pytest.approx(5.0)
    assert measured.base_area == pytest.approx(1.0)
    assert measured.volume is None
    assert measured.is_watertight is False
    assert "volume is unavailable" in "; ".join(measured.warnings)


def test_satellite_step_matches_fusion_validation_values() -> None:
    if not HAS_OCP:
        pytest.skip("STEP sample checks require cadmetrics[step]")

    sample = SAMPLES["satellite"]
    path = ROOT / sample["files"]["step"]
    expected = sample["expected"]

    measured = measure(path)
    projected_x = project(path)
    projected_alpha_60 = project(path, alpha_deg=60, output_unit="mm")

    assert measured.input_unit == "mm"
    assert measured.volume == pytest.approx(expected["volume"])
    assert measured.surface_area == pytest.approx(expected["surface_area"])
    assert projected_x.projected_area == pytest.approx(expected["projected_area_x"], rel=1.0e-3)
    assert projected_alpha_60.projected_area == pytest.approx(
        expected["projected_area_alpha_60"] * 1_000_000,
        rel=1.0e-3,
    )
    assert measured.is_watertight is True
