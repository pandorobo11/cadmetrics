from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path
from typing import Iterable

from cadmetrics.result_schema import RESULT_FIELD_SPECS
from cadmetrics.types import MeasurementRow

CSV_FIELDS = [spec.key for spec in RESULT_FIELD_SPECS]


def validate_csv_output_path(
    path: str | Path,
    *,
    protected_paths: Iterable[str | Path] = (),
) -> Path:
    output_path = Path(path)
    for protected_path in protected_paths:
        source_path = Path(protected_path)
        if _paths_refer_to_same_file(output_path, source_path):
            raise ValueError(f"CSV output path must not overwrite an input CAD file: {output_path}")
    return output_path


def write_rows_csv(
    path: str | Path,
    rows: Iterable[MeasurementRow],
    *,
    protected_paths: Iterable[str | Path] = (),
) -> None:
    protected = tuple(protected_paths)
    output_path = validate_csv_output_path(path, protected_paths=protected)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow(row.to_csv_row())
            handle.flush()
            os.fsync(handle.fileno())

        validate_csv_output_path(output_path, protected_paths=protected)
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _paths_refer_to_same_file(first: Path, second: Path) -> bool:
    try:
        if first.resolve(strict=False) == second.resolve(strict=False):
            return True
    except OSError:
        pass
    try:
        return first.samefile(second)
    except OSError:
        return False
