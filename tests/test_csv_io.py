from __future__ import annotations

import csv
import re
from dataclasses import fields, replace
import os
from pathlib import Path

import pytest

from cadmetrics.csv_io import CSV_FIELDS, write_rows_csv
from cadmetrics.result_schema import RESULT_FIELD_SPECS
from cadmetrics.types import MeasurementRow


def test_result_schema_defines_csv_order_and_measurement_row_serialization() -> None:
    row = replace(
        _row(),
        step_components=(1, 3),
        step_component_names=("Body", "Tail"),
        warnings=("first", "second"),
    )
    values = row.to_csv_row()
    schema_keys = [spec.key for spec in RESULT_FIELD_SPECS]

    assert CSV_FIELDS == schema_keys
    assert list(values) == schema_keys
    assert set(schema_keys) == {item.name for item in fields(MeasurementRow)}
    assert len(schema_keys) == len(set(schema_keys))
    assert all(spec.description and spec.gui_label for spec in RESULT_FIELD_SPECS)
    assert values["step_components"] == "1,3"
    assert values["step_component_names"] == "Body; Tail"
    assert values["warnings"] == "first; second"
    for spec in RESULT_FIELD_SPECS:
        if spec.key not in {"step_components", "step_component_names", "warnings"}:
            assert values[spec.key] == getattr(row, spec.key)


def test_documented_csv_schema_matches_registry() -> None:
    expected = [(spec.key, spec.description) for spec in RESULT_FIELD_SPECS]

    assert _requirements_csv_keys(Path("docs/requirements.md")) == [
        spec.key for spec in RESULT_FIELD_SPECS
    ]
    assert _cli_csv_fields(Path("docs/cli.md")) == expected


def test_csv_writer_preserves_schema_order_and_special_serialization(tmp_path: Path) -> None:
    output = tmp_path / "results.csv"
    row = replace(
        _row(),
        step_components=(1, 3),
        step_component_names=("Body", "Tail"),
        warnings=("first", "second"),
    )

    write_rows_csv(output, [row])

    with output.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        records = list(reader)
    assert reader.fieldnames == CSV_FIELDS
    assert list(records[0]) == CSV_FIELDS
    assert records[0]["file"] == "model.step"
    assert records[0]["pitch_deg"] == ""
    assert records[0]["is_watertight"] == "True"
    assert records[0]["step_components"] == "1,3"
    assert records[0]["step_component_names"] == "Body; Tail"
    assert records[0]["warnings"] == "first; second"


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


def _csv_section(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    section = text.split("## CSV Columns", 1)[1]
    return section.split("\n## ", 1)[0]


def _requirements_csv_keys(path: Path) -> list[str]:
    return re.findall(r"^- `([^`]+)`$", _csv_section(path), flags=re.MULTILINE)


def _cli_csv_fields(path: Path) -> list[tuple[str, str]]:
    return re.findall(
        r"^\| `([^`]+)` \| (.+) \|$",
        _csv_section(path),
        flags=re.MULTILINE,
    )
