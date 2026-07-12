from __future__ import annotations

import tempfile
from pathlib import Path


def spinbox_arrow_image_urls() -> tuple[str, str]:
    asset_dir = Path(tempfile.gettempdir()) / "cadmetrics-gui-assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    up = asset_dir / "spin-up.svg"
    down = asset_dir / "spin-down.svg"
    up.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="8" viewBox="0 0 10 8">'
        '<path d="M5 1 L9 6 H1 Z" fill="#43505d"/></svg>',
        encoding="utf-8",
    )
    down.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="8" viewBox="0 0 10 8">'
        '<path d="M1 2 H9 L5 7 Z" fill="#43505d"/></svg>',
        encoding="utf-8",
    )
    return up.as_posix(), down.as_posix()


def with_spinbox_assets(stylesheet: str) -> str:
    up, down = spinbox_arrow_image_urls()
    return stylesheet.replace("__SPIN_UP_URL__", up).replace("__SPIN_DOWN_URL__", down)
