from __future__ import annotations

import subprocess
from functools import lru_cache
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


@lru_cache(maxsize=1)
def cadmetrics_version() -> str:
    try:
        return version("cadmetrics")
    except PackageNotFoundError:
        return "unknown"


@lru_cache(maxsize=1)
def cadmetrics_hash() -> str:
    embedded = _embedded_git_hash()
    if embedded is not None:
        return embedded

    repo_root = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:
        return "unknown"

    if _tracked_worktree_is_dirty(repo_root):
        return f"{commit}-dirty"
    return commit


def _embedded_git_hash() -> str | None:
    try:
        build_info = import_module("cadmetrics._build")
    except Exception:
        return None
    value = getattr(build_info, "GIT_HASH", None)
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or value == "unknown":
        return None
    return value


def _tracked_worktree_is_dirty(repo_root: Path) -> bool:
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:
        return False
    return bool(status)
