"""Describe the selected CPython environment without importing the product GUI."""

from __future__ import annotations

import json
import os
import sys
import sysconfig
from pathlib import Path


def runtime_info() -> dict[str, str | None]:
    if sys.implementation.name != "cpython":
        raise RuntimeError("The macOS launcher requires CPython")
    candidates = []
    library = sysconfig.get_config_var("LDLIBRARY")
    libdir = sysconfig.get_config_var("LIBDIR")
    if library and libdir:
        candidates.append(Path(libdir) / library)
    framework = sysconfig.get_config_var("PYTHONFRAMEWORK")
    if framework:
        candidates.append(Path(sys.base_prefix) / framework)
        prefix = sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX")
        version = sysconfig.get_config_var("VERSION")
        if prefix and version:
            candidates.append(
                Path(prefix) / f"{framework}.framework/Versions/{version}/{framework}"
            )
    entry = Path(sysconfig.get_path("scripts")) / "cadmetrics-gui"
    if not entry.is_file() or not os.access(entry, os.X_OK):
        raise RuntimeError("cadmetrics-gui is missing; run uv sync --extra step --extra gui")
    for candidate in candidates:
        if candidate.is_file():
            return {
                # Keep the venv leaf; resolving the symlink loses pyvenv.cfg discovery.
                "executable": str(Path(sys.executable).absolute()),
                "library": str(candidate.resolve()),
                "entry": str(entry.absolute()),
                "path": os.environ.get("PATH", ""),
                "virtual_env": os.environ.get("VIRTUAL_ENV"),
            }
    raise RuntimeError("No CPython shared library found; use a shared/framework build")


if __name__ == "__main__":
    try:
        print(json.dumps(runtime_info()))
    except RuntimeError as exc:
        print(f"Cadmetrics runtime discovery failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
