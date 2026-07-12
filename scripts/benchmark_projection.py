from __future__ import annotations

import argparse
import json
import statistics
import tracemalloc
from pathlib import Path
from time import perf_counter

from cadmetrics.api import inspect_model, project_model


def benchmark_projection(path: Path, *, repeats: int) -> dict[str, int | float | str]:
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    model = inspect_model(path)
    durations: list[float] = []
    peak_bytes = 0
    projected_area = 0.0
    for _ in range(repeats):
        tracemalloc.start()
        started = perf_counter()
        row = project_model(model)
        durations.append(perf_counter() - started)
        _, current_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_bytes = max(peak_bytes, current_peak)
        projected_area = float(row.projected_area or 0.0)
    return {
        "file": str(path),
        "vertices": model.vertex_count,
        "triangles": model.face_count,
        "repeats": repeats,
        "median_seconds": statistics.median(durations),
        "min_seconds": min(durations),
        "peak_bytes": peak_bytes,
        "projected_area": projected_area,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark projected-area calculation.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(benchmark_projection(args.path, repeats=args.repeats), indent=2))


if __name__ == "__main__":
    main()
