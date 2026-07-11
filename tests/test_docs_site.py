from __future__ import annotations

from pathlib import Path

from cadmetrics.docs_site import build_documentation_site


def test_mkdocs_site_contains_readme_docs_and_assets(tmp_path: Path) -> None:
    site_dir = tmp_path / "site"

    build_documentation_site(Path.cwd(), site_dir)

    assert (site_dir / "index.html").is_file()
    assert (site_dir / "docs" / "gui.html").is_file()
    assert (site_dir / "docs" / "accuracy.html").is_file()
    assert (site_dir / "docs" / "assets" / "gui-main.png").is_file()
    index = (site_dir / "index.html").read_text(encoding="utf-8")
    assert "cadmetrics" in index
    assert "docs/gui.html" in index
