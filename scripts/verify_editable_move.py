"""Reproduce an editable checkout move in a new scratch directory, then recover it.

This checks real package and GUI entry-point imports. Native screen interaction is
separate; the launcher contract tests use a self-contained probe instead.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = ["uv", "sync", "--locked", "--extra", "step", "--extra", "gui", "--group", "dev"]


def verify(workspace: Path) -> dict[str, object]:
    workspace.mkdir(parents=True, exist_ok=False)
    old = workspace / "original checkout"
    moved = workspace / "moved checkout"
    old.mkdir()
    archive = workspace / "source.tar"
    subprocess.run(["git", "archive", "HEAD", "-o", str(archive)], cwd=ROOT, check=True)
    with tarfile.open(archive) as source:
        source.extractall(old, filter="data")
    env = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        env.pop(name, None)
    env["UV_PYTHON"] = str(Path(sys.executable).resolve())

    def run(args: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args, cwd=cwd, env=env, check=check, capture_output=True, text=True, timeout=300
        )

    print("Installing the real locked editable project before moving it...", flush=True)
    first_sync = run(SYNC, old)
    (workspace / "sync-before.log").write_text(first_sync.stderr, encoding="utf-8")
    python = old / ".venv/bin/python"
    purelib = Path(
        run(
            [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], old
        ).stdout.strip()
    )
    stale_pth = {
        path.name: path.read_text()
        for path in purelib.glob("*.pth")
        if str(old / "src") in path.read_text()
    }
    assert stale_pth, "The real editable install must reference the original src"
    if sys.platform == "darwin":
        run(
            [
                str(python),
                "scripts/create_macos_app.py",
                "--bundle-id",
                "local.cadmetrics.editable-move",
            ],
            old,
        )
    old.rename(moved)
    assert not old.exists()
    python = moved / ".venv/bin/python"
    discovery = run([str(python), "-I", "scripts/macos_runtime.py"], moved)
    runtime_info = json.loads(discovery.stdout)
    entry = Path(runtime_info["entry"])
    assert os.access(entry, os.X_OK)
    failed_entry = run([str(python), "-I", str(entry)], moved, check=False)
    missing_product = tuple(
        f"ModuleNotFoundError: No module named '{name}'"
        for name in ("cadmetrics", "cadmetrics.gui", "cadmetrics.gui.pyside_app")
    )
    assert failed_entry.returncode != 0, failed_entry.stderr
    assert any(error in failed_entry.stderr for error in missing_product), failed_entry.stderr
    native_before = None
    if sys.platform == "darwin":
        native_before = run(
            [str(moved / "dist/Cadmetrics.app/Contents/MacOS/Cadmetrics")], moved, check=False
        )
        assert native_before.returncode != 0, native_before.stderr
        assert any(error in native_before.stderr for error in missing_product), native_before.stderr

    print(
        "Discovery succeeded but the real moved GUI entry could not import cadmetrics.", flush=True
    )
    backup = Path(tempfile.mkdtemp(prefix=".venv-before-move.", dir=moved))
    (moved / ".venv").rename(backup / "venv")
    print("Recreating the environment with the documented locked uv sync command...", flush=True)
    recovered_sync = run(SYNC, moved)
    (workspace / "sync-after.log").write_text(recovered_sync.stderr, encoding="utf-8")
    verification = run(
        [
            str(python),
            "-I",
            "-c",
            """
import importlib.metadata as metadata
import json
import cadmetrics
from cadmetrics.gui import pyside_app
entry = next(e for e in metadata.distribution('cadmetrics').entry_points if e.name == 'cadmetrics-gui')
assert entry.group == 'gui_scripts' and entry.load() is pyside_app.main
print(json.dumps({'module_file': cadmetrics.__file__, 'gui_entry': entry.value,
                 'versions': {n: metadata.version(n) for n in ('PySide6', 'pyvista', 'pyvistaqt', 'cadquery-ocp')}}))
""",
        ],
        moved,
    )
    recovered = json.loads(verification.stdout)
    assert Path(recovered["module_file"]).resolve() == moved / "src/cadmetrics/__init__.py"
    if sys.platform == "darwin":
        run(
            [
                str(python),
                "scripts/create_macos_app.py",
                "--replace",
                "--bundle-id",
                "local.cadmetrics.editable-move",
            ],
            moved,
        )
    return {
        "source_commit": run(["git", "rev-parse", "HEAD"], ROOT).stdout.strip(),
        "platform": sys.platform,
        "old_checkout_unavailable": not old.exists(),
        "stale_editable_pth": stale_pth,
        "runtime_discovery_before_recovery": runtime_info,
        "gui_entry_before_recovery": {
            "exit": failed_entry.returncode,
            "stderr": failed_entry.stderr,
        },
        "native_entry_before_recovery": None
        if native_before is None
        else {"exit": native_before.returncode, "stderr": native_before.stderr},
        "recovered": recovered,
        "moved_checkout": str(moved),
        "gui_screen_workflow": "not exercised by this script",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace", type=Path, required=True, help="New scratch directory to retain"
    )
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    report = verify(workspace)
    destination = workspace / "report.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Editable recovery and GUI entry-point imports passed. Report: {destination}")


if __name__ == "__main__":
    main()
