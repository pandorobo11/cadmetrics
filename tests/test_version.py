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

    try:
        assert version_module.cadmetrics_hash() == "abc123def456"
    finally:
        version_module.cadmetrics_hash.cache_clear()
