from __future__ import annotations

import sys
from types import SimpleNamespace

from cadmetrics import version as version_module


def test_cadmetrics_hash_prefers_embedded_build_hash(monkeypatch) -> None:
    version_module.cadmetrics_hash.cache_clear()
    monkeypatch.setitem(
        sys.modules,
        "cadmetrics._build",
        SimpleNamespace(GIT_HASH="abc123def456"),
    )

    assert version_module.cadmetrics_hash() == "abc123def456"


def test_embedded_build_hash_ignores_unknown(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "cadmetrics._build",
        SimpleNamespace(GIT_HASH="unknown"),
    )

    assert version_module._embedded_git_hash() is None
