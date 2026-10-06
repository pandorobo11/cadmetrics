"""Native process contracts, independent of Qt and display availability."""

from __future__ import annotations

import importlib.util
import json
import os
import plistlib
import selectors
import signal
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAC_ONLY = pytest.mark.skipif(sys.platform != "darwin", reason="native macOS launcher")


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_script("create_macos_app")
runtime = load_script("macos_runtime")

PROBE = """
import ctypes
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time

def child(_):
    return (os.getpid(), sys.executable, sys.prefix)

if __name__ == "__main__":
    buffer = ctypes.create_string_buffer(4096)
    size = ctypes.c_uint32(len(buffer))
    assert ctypes.CDLL(None)._NSGetExecutablePath(buffer, ctypes.byref(size)) == 0
    with multiprocessing.get_context("spawn").Pool(1) as pool:
        worker = pool.map(child, [0])[0]
    print(json.dumps({
        "argv": sys.argv[1:], "pid": os.getpid(), "image": os.fsdecode(buffer.value),
        "executable": sys.executable, "prefix": sys.prefix, "cwd": os.getcwd(),
        "worker": worker, "qt_platform": os.environ.get("QT_QPA_PLATFORM"),
        "vtk_offscreen": os.environ.get("PYVISTA_OFF_SCREEN"),
        "path": os.environ.get("PATH"), "virtual_env": os.environ.get("VIRTUAL_ENV"),
    }), flush=True)
    if "--wait" in sys.argv:
        time.sleep(60)
    raise SystemExit(int(os.environ.get("PROBE_EXIT", "0")))
"""


@pytest.mark.parametrize("framework", [False, True])
def test_runtime_discovery_preserves_venv_and_finds_library(tmp_path, monkeypatch, framework):
    library = tmp_path / ("Python" if framework else "libpython.dylib")
    library.touch()
    entry = tmp_path / "cadmetrics-gui"
    entry.touch(mode=0o755)
    values = {
        "LDLIBRARY": "missing" if framework else library.name,
        "LIBDIR": str(tmp_path),
        "PYTHONFRAMEWORK": "Python" if framework else None,
    }
    monkeypatch.setattr(runtime.sysconfig, "get_config_var", values.get)
    monkeypatch.setattr(runtime.sysconfig, "get_path", lambda _: str(tmp_path))
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path))
    monkeypatch.setattr(sys, "executable", str(tmp_path / "venv/bin/python"))
    assert runtime.runtime_info() == {
        "executable": str(tmp_path / "venv/bin/python"),
        "library": str(library),
        "entry": str(entry),
        "path": os.environ.get("PATH", ""),
        "virtual_env": os.environ.get("VIRTUAL_ENV"),
    }
    library.unlink()
    with pytest.raises(RuntimeError, match="shared library"):
        runtime.runtime_info()
    entry.unlink()
    with pytest.raises(RuntimeError, match="cadmetrics-gui is missing"):
        runtime.runtime_info()


def test_build_metadata_and_failed_rebuild_preserve_existing_app(tmp_path, monkeypatch):
    monkeypatch.setattr(builder.sys, "platform", "darwin")

    def compile_stub(args, **kwargs):
        Path(args[-1]).write_bytes(b"compiled probe")

    monkeypatch.setattr(builder.subprocess, "run", compile_stub)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_bytes((ROOT / "pyproject.toml").read_bytes())
    output = tmp_path / "output"
    app = builder.build_app(repo, output, "test.cadmetrics")
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert info["CFBundleShortVersionString"] == project["version"]
    assert info["CFBundleVersion"] == project["version"]
    assert info["CFBundleExecutable"] == "Cadmetrics"
    assert info["CFBundleIdentifier"] == "test.cadmetrics"
    resources = app / "Contents/Resources"
    config = json.loads((resources / "launcher.json").read_text())
    assert (resources / config["repo"]).resolve() == repo
    assert (resources / "macos_runtime.py").read_bytes() == (
        ROOT / "scripts/macos_runtime.py"
    ).read_bytes()
    with pytest.raises(FileExistsError, match="--replace"):
        builder.build_app(repo, output, "test.cadmetrics")

    def broken_compile(args, **kwargs):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(builder.subprocess, "run", broken_compile)
    with pytest.raises(subprocess.CalledProcessError):
        builder.build_app(repo, output, "new.cadmetrics", replace=True)
    assert plistlib.loads((app / "Contents/Info.plist").read_bytes()) == info
    assert (app / "Contents/MacOS/Cadmetrics").read_bytes() == b"compiled probe"
    monkeypatch.setattr(builder.subprocess, "run", compile_stub)
    builder.build_app(repo, output, "new.cadmetrics", replace=True)
    assert (
        plistlib.loads((app / "Contents/Info.plist").read_bytes())["CFBundleIdentifier"]
        == "new.cadmetrics"
    )


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout with spaces 日本語 'quote'"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname="launcher-probe"\nversion="0.0.0"\nrequires-python=">=3.12,<3.13"\n'
    )
    return root


@MAC_ONLY
@pytest.mark.parametrize("use_uv", [False, True], ids=["venv", "uv-fallback"])
def test_native_argv_spawn_exit_and_restart_after_move(checkout, use_uv):
    env = dict(os.environ, UV_OFFLINE="1", UV_PYTHON=sys.executable)
    env["UV_CACHE_DIR"] = str(checkout.parent / "uv-cache")
    prefix_name = ".uv-env" if use_uv else ".venv"
    if use_uv:
        # Exercise actual uv selection without downloading packages or changing the real venv.
        env["UV_PROJECT_ENVIRONMENT"] = prefix_name
        subprocess.run(
            ["uv", "sync", "--offline"],
            cwd=checkout,
            env=env,
            check=True,
            capture_output=True,
            timeout=30,
        )
    else:
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(checkout / prefix_name)],
            check=True,
            capture_output=True,
            timeout=30,
        )
    entry = checkout / prefix_name / "bin/cadmetrics-gui"
    entry.write_text(PROBE)
    entry.chmod(0o755)
    builder.build_app(checkout, checkout / "dist", "test.cadmetrics")
    moved = checkout.with_name("moved checkout 日本語 'quote'")
    checkout.rename(moved)
    executable = moved / "dist/Cadmetrics.app/Contents/MacOS/Cadmetrics"
    args = ["--example", "space and 日本語", "$(literal);`value`", "'quoted'", ""]
    env.update(QT_QPA_PLATFORM="offscreen", PYVISTA_OFF_SCREEN="true")
    for status in (7, 0):
        env["PROBE_EXIT"] = str(status)
        with subprocess.Popen(
            [str(executable), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        ) as process:
            try:
                stdout, stderr = process.communicate(timeout=45)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise
            assert process.returncode == status, stderr
            info = json.loads(stdout)
            assert info["pid"] == process.pid
        assert Path(info["image"]).resolve() == executable.resolve()
        prefix = moved / prefix_name
        assert Path(info["prefix"]).resolve() == prefix.resolve()
        assert Path(info["executable"]).parent.resolve() == (prefix / "bin").resolve()
        assert Path(info["cwd"]).resolve() == moved.resolve()
        assert info["argv"] == args
        assert info["worker"][0] != info["pid"]
        assert info["worker"][1:] == [info["executable"], info["prefix"]]
        assert info["qt_platform"] == "offscreen"
        assert info["vtk_offscreen"] == "true"
        if use_uv:
            assert Path(info["virtual_env"]).resolve() == prefix.resolve()
            assert Path(info["path"].split(os.pathsep)[0]).resolve() == (prefix / "bin").resolve()
        else:
            assert info["virtual_env"] == env.get("VIRTUAL_ENV")
            assert info["path"].startswith("/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:")
    with subprocess.Popen(
        [str(executable), "--wait"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    ) as process:
        try:
            # The child marks readiness; terminate the native process, not a wrapper parent.
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                assert selector.select(timeout=30), "probe did not become ready"
            info = json.loads(process.stdout.readline())
            assert info["pid"] == process.pid
            process.terminate()
            process.communicate(timeout=15)
            assert process.returncode == -signal.SIGTERM
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


@MAC_ONLY
@pytest.mark.parametrize("invalid", ["json", "library", "entry"])
def test_invalid_runtime_fails_before_entry_point(checkout, invalid):
    python = checkout / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    entry = python.with_name("cadmetrics-gui")
    entry.write_text('raise AssertionError("GUI must not start")\n')
    entry.chmod(0o755)
    app = builder.build_app(checkout, checkout / "dist", "test.cadmetrics")
    probe = app / "Contents/Resources/macos_runtime.py"
    payload = {
        "executable": str(python),
        "library": "/missing/library",
        "entry": str(entry),
        "path": os.environ.get("PATH", ""),
        "virtual_env": None,
    }
    if invalid == "entry":
        payload["library"] = runtime.runtime_info()["library"]
        payload["entry"] = "/missing/entry"
    probe.write_text(
        'print("not JSON")' if invalid == "json" else f"print({json.dumps(json.dumps(payload))})"
    )
    result = subprocess.run(
        [str(app / "Contents/MacOS/Cadmetrics")], capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert (
        "invalid runtime information" in result.stderr
        if invalid == "json"
        else "no longer available" in result.stderr
    )
    assert "GUI must not start" not in result.stderr
