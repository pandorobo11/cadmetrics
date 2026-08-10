from __future__ import annotations

import os
from pathlib import Path

import pytest

from cadmetrics.csv_io import write_rows_csv
from cadmetrics.types import MeasurementRow


def test_csv_writer_rejects_input_path_without_modifying_it(tmp_path: Path) -> None:
    source = tmp_path / "model.step"
    original = b"STEP source data"
    source.write_bytes(original)

    with pytest.raises(ValueError, match="must not overwrite an input CAD file"):
        write_rows_csv(source, [_row()], protected_paths=[source])

    assert source.read_bytes() == original


@pytest.mark.parametrize("link_kind", ["symbolic", "hard"])
def test_csv_writer_rejects_alias_of_input_path(tmp_path: Path, link_kind: str) -> None:
    source = tmp_path / "model.step"
    source.write_bytes(b"STEP source data")
    alias = tmp_path / "results.csv"
    if link_kind == "symbolic":
        alias.symlink_to(source)
    else:
        os.link(source, alias)

    with pytest.raises(ValueError, match="must not overwrite an input CAD file"):
        write_rows_csv(alias, [_row()], protected_paths=[source])

    assert source.read_bytes() == b"STEP source data"


def test_csv_writer_preserves_existing_output_when_rows_fail(tmp_path: Path) -> None:
    output = tmp_path / "results.csv"
    output.write_text("existing output\n", encoding="utf-8")

    def failing_rows():
        yield _row()
        raise RuntimeError("row generation failed")

    with pytest.raises(RuntimeError, match="row generation failed"):
        write_rows_csv(output, failing_rows())

    assert output.read_text(encoding="utf-8") == "existing output\n"
    assert list(tmp_path.glob(".results.csv.*.tmp")) == []


def _row() -> MeasurementRow:
    return MeasurementRow(
        file="model.step",
        input_unit="m",
        output_unit="m",
        roll_deg=0.0,
        alpha_deg=0.0,
        beta_deg=0.0,
        volume=1.0,
        surface_area=6.0,
        projected_area=1.0,
        is_watertight=True,
    )
