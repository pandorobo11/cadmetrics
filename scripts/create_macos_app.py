from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


DEFAULT_BUNDLE_ID = "local.cadmetrics.gui"


def build_app(repo: Path, output: Path, bundle_id: str, *, replace: bool = False) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError(
            "The native macOS app must be built on macOS with Xcode Command Line Tools"
        )
    repo = repo.resolve()
    output = output.resolve()
    app = output / "Cadmetrics.app"
    if app.exists() and not replace:
        raise FileExistsError(f"{app} already exists; close it and use --replace to rebuild")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cadmetrics-build-", dir=output) as temporary:
        staging = Path(temporary) / "Cadmetrics.app"
        _build_bundle(repo, staging, app, bundle_id)
        backup = Path(temporary) / "previous.app"
        if app.exists():
            app.rename(backup)
        try:
            staging.rename(app)
        except OSError:
            if backup.exists():
                backup.rename(app)
            raise
    return app


def _build_bundle(repo: Path, app: Path, destination: Path, bundle_id: str) -> None:
    contents = app / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"

    macos.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)

    version = _project_version(repo)
    info = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleDisplayName": "Cadmetrics",
        "CFBundleExecutable": "Cadmetrics",
        "CFBundleIdentifier": bundle_id,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "Cadmetrics",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSApplicationCategoryType": "public.app-category.graphics-design",
        "NSHighResolutionCapable": True,
    }
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)

    # Compute this against the final location, not the temporary build directory.
    (resources / "launcher.json").write_text(
        json.dumps({"repo": os.path.relpath(repo, destination / "Contents" / "Resources")}),
        encoding="utf-8",
    )
    scripts = Path(__file__).resolve().parent
    shutil.copyfile(scripts / "macos_runtime.py", resources / "macos_runtime.py")
    subprocess.run(
        [
            "xcrun",
            "clang",
            "-fobjc-arc",
            "-framework",
            "Foundation",
            str(scripts / "macos_launcher.m"),
            "-o",
            str(macos / "Cadmetrics"),
        ],
        check=True,
    )

    (contents / "PkgInfo").write_text("APPL????", encoding="ascii")


def _project_version(repo: Path) -> str:
    pyproject = repo / "pyproject.toml"
    try:
        with pyproject.open("rb") as handle:
            version = tomllib.load(handle)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Could not read project version from {pyproject}") from exc
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"Invalid project version in {pyproject}")
    return version.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the native macOS development app.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dist"))
    parser.add_argument(
        "--bundle-id", default=os.environ.get("CADMETRICS_BUNDLE_ID", DEFAULT_BUNDLE_ID)
    )
    parser.add_argument("--replace", action="store_true", help="Replace an existing, closed app")
    args = parser.parse_args()

    repo = args.repo.resolve()
    output = args.output.resolve()
    app = build_app(repo, output, args.bundle_id, replace=args.replace)
    print(app)


if __name__ == "__main__":
    main()
