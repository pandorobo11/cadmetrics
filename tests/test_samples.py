from __future__ import annotations

import json
import importlib.util
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
