from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from cadmetrics.api import measure, project


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = json.loads((ROOT / "samples" / "metadata.json").read_text(encoding="utf-8"))["samples"]
HAS_OCP = importlib.util.find_spec("OCP") is not None


@pytest.mark.parametrize("sample_name", sorted(SAMPLES))
def test_sample_files_load(sample_name: str) -> None:
    sample = SAMPLES[sample_name]
    for relative_path in sample["files"].values():
        if relative_path is None:
            continue
        if relative_path.endswith(".step") and not HAS_OCP:
            pytest.skip("STEP sample checks require cadmetrics[step]")

        path = ROOT / relative_path
        measured = measure(path)
        projected = project(path)

        assert measured.surface_area is not None
        assert projected.projected_area is not None


@pytest.mark.parametrize("kind", ["ascii_stl", "binary_stl", "step"])
def test_box_sample_exact_metrics(kind: str) -> None:
    if kind == "step" and not HAS_OCP:
        pytest.skip("STEP sample checks require cadmetrics[step]")
    path = ROOT / SAMPLES["box_1x2x3"]["files"][kind]
    measured = measure(path)
    projected = project(path)

    assert measured.volume == pytest.approx(6.0)
    assert measured.surface_area == pytest.approx(22.0)
    assert projected.projected_area == pytest.approx(6.0)
    assert measured.is_watertight is True


@pytest.mark.parametrize("kind", ["ascii_stl", "binary_stl", "step"])
def test_overlap_sample_counts_projected_silhouette_once(kind: str) -> None:
    if kind == "step" and not HAS_OCP:
        pytest.skip("STEP sample checks require cadmetrics[step]")
    path = ROOT / SAMPLES["two_boxes_overlap_projection"]["files"][kind]
    projected = project(path)
    assert projected.projected_area == pytest.approx(1.0)


@pytest.mark.parametrize("kind", ["ascii_stl", "binary_stl"])
def test_intersecting_boxes_stl_keeps_raw_component_measurements(kind: str) -> None:
    path = ROOT / SAMPLES["two_boxes_intersecting"]["files"][kind]
    expected = SAMPLES["two_boxes_intersecting"]["expected"]

    measured = measure(path)
    projected = project(path)

    assert measured.volume == pytest.approx(expected["volume_stl"])
    assert measured.surface_area == pytest.approx(expected["surface_area_stl"])
    assert projected.projected_area == pytest.approx(expected["projected_area_x"])
    assert measured.is_watertight is True


def test_intersecting_boxes_step_uses_boolean_union_for_measurements() -> None:
    if not HAS_OCP:
        pytest.skip("STEP sample checks require cadmetrics[step]")
    path = ROOT / SAMPLES["two_boxes_intersecting"]["files"]["step"]
    expected = SAMPLES["two_boxes_intersecting"]["expected"]

    measured = measure(path)
    projected = project(path)

    assert measured.volume == pytest.approx(expected["volume_step"])
    assert measured.surface_area == pytest.approx(expected["surface_area_step"])
    assert projected.projected_area == pytest.approx(expected["projected_area_x"])
    assert measured.is_watertight is True


@pytest.mark.parametrize("kind", ["ascii_stl", "binary_stl", "step"])
def test_frame_sample_preserves_hole_in_z_projection(kind: str) -> None:
    if kind == "step" and not HAS_OCP:
        pytest.skip("STEP sample checks require cadmetrics[step]")
    path = ROOT / SAMPLES["frame_with_hole"]["files"][kind]
    measured = measure(path)
    projected = project(path, direction="0,0,1")

    assert measured.volume == pytest.approx(0.8)
    assert measured.surface_area == pytest.approx(17.6)
    assert projected.projected_area == pytest.approx(8.0)
    assert measured.is_watertight is True


@pytest.mark.parametrize("kind", ["ascii_stl", "binary_stl"])
def test_open_cube_sample_warns_about_non_watertight_mesh(kind: str) -> None:
    path = ROOT / SAMPLES["open_cube_missing_face"]["files"][kind]
    measured = measure(path)

    assert measured.surface_area == pytest.approx(5.0)
    assert measured.is_watertight is False
    assert measured.warnings


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
