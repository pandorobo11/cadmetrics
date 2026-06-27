from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from cadmetrics.cli import CSV_FIELDS
from cadmetrics.types import MeasurementRow


def write_rows_csv(path: str | Path, rows: Iterable[MeasurementRow]) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())
