from __future__ import annotations

import argparse
import os
import plistlib
import stat
from pathlib import Path


DEFAULT_BUNDLE_ID = "local.cadmetrics.gui"


def build_app(repo: Path, output: Path, bundle_id: str) -> Path:
    app = output / "Cadmetrics.app"
    contents = app / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"

    macos.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)

    info = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleDisplayName": "Cadmetrics",
        "CFBundleExecutable": "Cadmetrics",
        "CFBundleIdentifier": bundle_id,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "Cadmetrics",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "LSApplicationCategoryType": "public.app-category.graphics-design",
        "NSHighResolutionCapable": True,
    }
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)

    launcher = macos / "Cadmetrics"
    launcher.write_text(
        "\n".join(
            [
                "#!/bin/zsh",
                "set -euo pipefail",
                f"REPO={str(repo)!r}",
                'export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"',
                'cd "$REPO"',
                'if [ -x "$REPO/.venv/bin/cadmetrics-gui" ]; then',
                '  exec "$REPO/.venv/bin/cadmetrics-gui"',
                "fi",
                'exec uv run cadmetrics-gui',
                "",
            ]
        ),
        encoding="utf-8",
    )
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    (contents / "PkgInfo").write_text("APPL????", encoding="ascii")
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a lightweight macOS app wrapper.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dist"))
    parser.add_argument("--bundle-id", default=os.environ.get("CADMETRICS_BUNDLE_ID", DEFAULT_BUNDLE_ID))
    args = parser.parse_args()

    repo = args.repo.resolve()
    output = args.output.resolve()
    app = build_app(repo, output, args.bundle_id)
    print(app)


if __name__ == "__main__":
    main()
