"""Locate the sample geometry shipped with cadmetrics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class SampleInfo:
    name: str
    description: str
    files: tuple[Path, ...]


def samples_dir() -> Path:
    """Return the sample geometry directory.

    An installed wheel carries the subset chosen by :func:`packaged_sample_files`; a source
    checkout uses the full ``samples/`` tree.
    """
    packaged = resources.files("cadmetrics").joinpath("_samples")
    if packaged.is_dir():
        return Path(str(packaged))
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "samples"
        if (candidate / "metadata.json").is_file():
            return candidate
    raise FileNotFoundError("cadmetrics sample geometry was not found.")


def packaged_sample_files(samples: Path) -> list[Path]:
    """Return the files of a ``samples/`` tree that the wheel bundles.

    ASCII STL duplicates the binary STL in a text encoding several times larger, so only the
    small unit-cube ASCII STL is kept as an example of that format. The build hook loads this
    module by path, so it must stay importable with the standard library alone.
    """
    files = [samples / "metadata.json", samples / "unit_cube" / "unit_cube_ascii.stl"]
    files += sorted(samples.glob("*/*.step"))
    files += sorted(samples.glob("*/*_binary.stl"))
    return [path for path in files if path.is_file()]


def list_samples() -> list[SampleInfo]:
    """Return the samples described in ``metadata.json`` with the files that are present."""
    directory = samples_dir()
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    samples = []
    for name, entry in metadata["samples"].items():
        files = []
        for path in entry["files"].values():
            if path is None:
                continue
            # metadata.json stores repository-relative paths such as samples/x/x.step.
            resolved = directory / Path(path).relative_to("samples")
            if resolved.is_file():
                files.append(resolved)
        samples.append(SampleInfo(name=name, description=entry["description"], files=tuple(files)))
    return samples
