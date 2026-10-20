from __future__ import annotations

from pathlib import Path

from cadmetrics.samples import list_samples, packaged_sample_files


SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def test_list_samples_resolves_metadata_files() -> None:
    samples = {sample.name: sample for sample in list_samples()}

    assert [file.name for file in samples["multi_file_step_components"].files] == [
        "box_pair_a.step",
        "box_pair_b.step",
    ]
    assert all(file.is_file() for sample in samples.values() for file in sample.files)


def test_wheel_sample_subset_drops_ascii_stl_but_keeps_every_sample() -> None:
    packaged = {path.relative_to(SAMPLES).as_posix() for path in packaged_sample_files(SAMPLES)}

    assert "metadata.json" in packaged
    assert {name for name in packaged if name.endswith("_ascii.stl")} == {
        "unit_cube/unit_cube_ascii.stl"
    }
    for sample in list_samples():
        assert any(file.relative_to(SAMPLES).as_posix() in packaged for file in sample.files)
