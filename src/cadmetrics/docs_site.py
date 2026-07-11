from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


def build_documentation_site(project_root: Path, site_dir: Path) -> None:
    try:
        from mkdocs.commands.build import build
        from mkdocs.config import load_config
    except ImportError as exc:
        raise RuntimeError(
            "Building the documentation requires MkDocs. Run: uv sync --extra step --extra gui"
        ) from exc

    project_root = project_root.resolve()
    site_dir = site_dir.resolve()
    with tempfile.TemporaryDirectory(prefix="cadmetrics-mkdocs-") as temporary:
        source_dir = Path(temporary) / "source"
        source_dir.mkdir()
        shutil.copy2(project_root / "README.md", source_dir / "index.md")
        shutil.copytree(project_root / "docs", source_dir / "docs")
        shutil.copy2(project_root / "LICENSE", source_dir / "LICENSE")
        metadata = project_root / "samples" / "metadata.json"
        if metadata.is_file():
            destination = source_dir / "samples" / "metadata.json"
            destination.parent.mkdir()
            shutil.copy2(metadata, destination)

        config = load_config(config_file=str(project_root / "mkdocs.yml"))
        config["docs_dir"] = str(source_dir)
        config["site_dir"] = str(site_dir)
        build(config)
