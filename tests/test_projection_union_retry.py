from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cadmetrics.projection import (
    ProjectionUnionError,
    projected_metrics,
    projection_basis,
)
from cadmetrics.types import ModelData

shapely = pytest.importorskip("shapely")

# Minimal reproduction of GEOS "AssertionFailedException: found two shells in
# EdgeRing list" from shapely.union_all. Three triangles taken from the
# 16-part scripts/benchmark_step_load.py synthetic assembly (mesh auto, metres)
# projected along alpha=180, beta=60. They are near edge-on slivers whose z
# coordinates around -3 mm differ by one ulp, so they survive the exact
# constant-coordinate filter and leave almost collinear edges for GEOS to node.
SLIVER_DIRECTION = (-0.5000000000000001, -0.8660254037844386, 0.0)
SLIVER_TRIANGLES = (
    (
        (0.06774343733048814, 0.08526808394863411, -0.002999067546002448),
        (0.0673743528562905, 0.08497225135357986, -0.0029990675460024496),
        (0.06761579853889084, 0.08534608239053511, -0.0029990675460024496),
    ),
    (
        (0.05762315558730691, 0.06844780722236073, -0.0029916113915435423),
        (0.05801395439682237, 0.0687014343279001, -0.0029990675460024496),
        (0.05804719862505165, 0.06855578184728435, -0.0029916113915435423),
    ),
    (
        (0.05147248485175474, 0.056896238313784535, -0.002999067546002448),
        (0.0513283754747617, 0.05732515807912749, -0.002999067546002448),
        (0.05147131402108774, 0.05736924878147614, -0.0029990675460024496),
    ),
)


@pytest.fixture
def sliver_model() -> ModelData:
    vertices = np.asarray(SLIVER_TRIANGLES, dtype=float).reshape(-1, 3)
    return ModelData(
        path=Path("sliver_triangles.stl"),
        source_format="stl",
        vertices=vertices,
        faces=np.arange(vertices.shape[0], dtype=np.int64).reshape(-1, 3),
        input_unit="m",
        output_unit="m",
        volume=None,
        surface_area=None,
        base_area=None,
        is_watertight=False,
    )


def _projected_polygons(model: ModelData) -> np.ndarray:
    basis_u, basis_v = projection_basis(np.asarray(SLIVER_DIRECTION))
    projected = np.column_stack((model.vertices @ basis_u, model.vertices @ basis_v))
    return shapely.polygons(projected[model.faces])


def test_sliver_fixture_reproduces_geos_assertion(sliver_model: ModelData) -> None:
    with pytest.raises(shapely.errors.GEOSException, match="found two shells"):
        shapely.union_all(_projected_polygons(sliver_model))


def test_projected_metrics_recovers_from_geos_assertion(sliver_model: ModelData) -> None:
    polygons = _projected_polygons(sliver_model)
    # The pairwise overlaps are below 1e-34, so the outline area is the plain sum.
    expected = float(np.sum(shapely.area(polygons)))

    metrics = projected_metrics(sliver_model, direction=np.asarray(SLIVER_DIRECTION))

    assert metrics.area == pytest.approx(expected, rel=1.0e-9, abs=0.0)
    assert metrics.centroid_u is not None and np.isfinite(metrics.centroid_u)
    assert metrics.centroid_v is not None and np.isfinite(metrics.centroid_v)


def test_projected_metrics_reports_unrecoverable_union(
    sliver_model: ModelData, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_fail(*args: object, **kwargs: object) -> object:
        raise shapely.errors.GEOSException("AssertionFailedException: synthetic failure")

    monkeypatch.setattr(shapely, "union_all", always_fail)

    with pytest.raises(ProjectionUnionError) as error:
        projected_metrics(sliver_model, direction=np.asarray(SLIVER_DIRECTION))

    message = str(error.value)
    assert "3 projected triangles" in message
    assert "(-0.5000000000000001, -0.8660254037844386, 0.0)" in message
    assert "synthetic failure" in message
    assert isinstance(error.value.__cause__, shapely.errors.GEOSException)
