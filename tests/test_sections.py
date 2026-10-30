from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

pytest.importorskip("shapely")
trimesh = pytest.importorskip("trimesh")

from cadmetrics.api import inspect_model, sections  # noqa: E402
from cadmetrics.cli import app  # noqa: E402
from cadmetrics.sections import (  # noqa: E402
    calculate_sections,
    fitted_area_slope,
    section_outline,
    sears_haack_area,
    sears_haack_area_slope,
    sears_haack_drag_area,
    theta_angles,
    wave_drag_area,
    wave_drag_spectrum,
    wind_axes,
)
from cadmetrics.orientation import (  # noqa: E402
    Orientation,
    projection_direction_for_orientation,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
DATA_DIR = Path(__file__).parent / "data"


def _write_mesh(path: Path, mesh: object) -> Path:
    mesh.export(path)  # type: ignore[attr-defined]
    return path


def _box(tmp_path: Path, *, faces_transform=None, name: str = "box.stl") -> Path:
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    mesh.apply_translation((0.5, 0.0, 0.0))
    faces = np.asarray(mesh.faces, dtype=np.int64).copy()
    if faces_transform is not None:
        faces = faces_transform(faces)
    mesh = trimesh.Trimesh(vertices=mesh.vertices.copy(), faces=faces, process=False)
    return _write_mesh(tmp_path / name, mesh)


def test_theta_angles_cover_the_circle_with_equal_weights() -> None:
    angles = theta_angles(16)

    assert len(angles) == 16
    assert [theta for theta, _ in angles][:3] == [-157.5, -135.0, -112.5]
    assert 180.0 in [theta for theta, _ in angles]
    assert sum(weight for _, weight in angles) == pytest.approx(1.0)


def test_symmetric_theta_angles_keep_one_of_each_mirror_pair() -> None:
    angles = theta_angles(16, symmetric=True)

    assert [theta for theta, _ in angles] == [
        -90.0,
        -67.5,
        -45.0,
        -22.5,
        0.0,
        22.5,
        45.0,
        67.5,
        90.0,
    ]
    weights = dict(angles)
    assert weights[90.0] == pytest.approx(1 / 16)
    assert weights[0.0] == pytest.approx(2 / 16)
    assert sum(weights.values()) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="even"):
        theta_angles(15, symmetric=True)


def test_box_sections_are_flat_with_an_empty_first_plane() -> None:
    result = sections(SAMPLES / "box_1x2x3" / "box_1x2x3_binary.stl", section_count=11)
    series = result.series[0]

    assert series.theta_deg is None
    assert series.area[0] == 0.0
    # The last plane gives the section just before the flat base.
    assert series.area[1:] == pytest.approx(np.full(10, 6.0))
    assert series.x[0] == pytest.approx(result.model.x_min)
    assert series.x[-1] == pytest.approx(result.model.x_max)
    assert "blunt" in "; ".join(result.warnings)


def test_cylinder_step_sections_match_the_circle_area() -> None:
    pytest.importorskip("OCP")
    result = sections(SAMPLES / "cylinder_x_r1_l2" / "cylinder_x_r1_l2.step")
    interior = result.series[0].area[1:]

    assert interior == pytest.approx(np.full(interior.shape, math.pi), rel=0.01)


def test_frame_hole_splits_the_section() -> None:
    result = sections(SAMPLES / "frame_with_hole" / "frame_with_hole_binary.stl", section_count=7)
    area = result.series[0].area

    # Through the hole only the two side bars are cut.
    assert area[3] == pytest.approx(0.2)
    assert area[1] == pytest.approx(0.3)


def test_overlapping_bodies_are_counted_once() -> None:
    intersecting = sections(
        SAMPLES / "two_boxes_intersecting" / "two_boxes_intersecting_binary.stl"
    )
    duplicate = sections([DATA_DIR / "unit_cube.stl", DATA_DIR / "unit_cube.stl"], section_count=5)

    assert intersecting.model.volume == pytest.approx(2.0)
    assert intersecting.series[0].max_area == pytest.approx(1.0)
    assert duplicate.series[0].area[1:] == pytest.approx(np.ones(4))


@pytest.mark.parametrize(
    "transform",
    [
        pytest.param(lambda faces: faces[:, ::-1], id="inside-out"),
        pytest.param(lambda faces: np.vstack((faces[:1, ::-1], faces[1:])), id="one-flipped-face"),
    ],
)
def test_face_orientation_does_not_change_the_area(tmp_path: Path, transform) -> None:
    result = sections(_box(tmp_path, faces_transform=transform), section_count=5)

    assert result.series[0].area[1:] == pytest.approx(np.ones(4))
    assert len(result.warnings) == 1
    assert result.warnings[0].startswith("The body starts with a blunt face")


def _boxes(tmp_path: Path, *specs: tuple[tuple[float, ...], tuple[float, ...], bool]) -> Path:
    """One STL of boxes given as (extents, center, inside_out)."""

    meshes = []
    for extents, center, inside_out in specs:
        box = trimesh.creation.box(extents=extents)
        box.apply_translation(center)
        if inside_out:
            box.invert()
        meshes.append(box)
    path = tmp_path / f"boxes{len(list(tmp_path.glob('boxes*.stl')))}.stl"
    return _write_mesh(path, trimesh.util.concatenate(meshes))


def test_inside_out_parts_count_like_the_others(tmp_path: Path) -> None:
    cube = (1.0, 1.0, 1.0)
    normal = _boxes(tmp_path, (cube, (0.5, -1.0, 0.0), False))
    inside_out = _boxes(tmp_path, (cube, (0.5, 1.0, 0.0), True))
    larger_inside_out = _boxes(tmp_path, ((2.0, 2.0, 2.0), (1.0, 1.5, 0.0), True))
    overlapping = _boxes(tmp_path, (cube, (0.5, -0.5, 0.0), True))

    side_by_side = sections([normal, inside_out], section_count=5)
    assert side_by_side.series[0].area == pytest.approx([0.0, 2.0, 2.0, 2.0, 2.0])
    # The larger part used to decide the orientation for the whole mesh.
    larger = sections([normal, larger_inside_out], section_count=5)
    assert larger.series[0].area == pytest.approx([0.0, 5.0, 5.0, 4.0, 4.0])
    union = sections([normal, overlapping], section_count=5)
    assert union.series[0].area == pytest.approx([0.0, 1.5, 1.5, 1.5, 1.5])
    assert not any("opposite ways" in warning for warning in union.warnings)


@pytest.mark.parametrize("inside_out", [False, True])
def test_cavities_stay_empty(tmp_path: Path, inside_out: bool) -> None:
    hollow = _boxes(
        tmp_path,
        ((2.0, 2.0, 2.0), (0.0, 0.0, 0.0), inside_out),
        ((1.0, 1.0, 1.0), (0.0, 0.0, 0.0), not inside_out),
    )
    separate = _boxes(tmp_path, ((1.0, 1.0, 1.0), (0.5, 1.0, 0.0), not inside_out))

    result = sections(hollow, section_count=9)
    assert result.series[0].area == pytest.approx([0, 4, 4, 3, 3, 3, 3, 4, 4])
    assert result.model.volume == pytest.approx(7.0)
    # A solid facing the other way, half inside the wall and half outside.
    together = sections([hollow, separate], section_count=9)
    assert together.series[0].area == pytest.approx([0, 4, 4, 3, 3, 3.5, 3.5, 4.5, 4.5])


def test_shells_that_cannot_be_told_from_cavities_are_warned(tmp_path: Path) -> None:
    # An inside-out box crossing the surface of a sphere: neither solid nor cavity.
    sphere = trimesh.creation.icosphere(subdivisions=3)
    box = trimesh.creation.box(extents=(0.4, 0.4, 0.4))
    box.apply_translation((0.0, 0.6, 0.6))
    box.invert()
    path = _write_mesh(tmp_path / "crossing.stl", trimesh.util.concatenate([sphere, box]))
    result = sections(path, section_count=21)

    assert any("opposite ways" in warning for warning in result.warnings)
    # Even-odd filling still counts the sphere where the box is not.
    assert result.series[0].max_area == pytest.approx(math.pi, rel=0.05)


def test_parts_that_share_edges_are_warned(tmp_path: Path) -> None:
    cube = (1.0, 1.0, 1.0)
    normal = _boxes(tmp_path, (cube, (0.5, 0.0, 0.0), False))
    touching = _boxes(tmp_path, (cube, (0.5, 1.0, 0.0), False))
    touching_inside_out = _boxes(tmp_path, (cube, (0.5, 1.0, 0.0), True))
    apart_inside_out = _boxes(tmp_path, (cube, (0.5, 2.0, 0.0), True))

    outward = sections([normal, touching], section_count=5)
    assert outward.series[0].area == pytest.approx([0.0, 2.0, 2.0, 2.0, 2.0])
    assert any("shared edges" in warning for warning in outward.warnings)
    # Joined into one shell, the inside-out part cannot be turned around, so it is warned.
    inside_out = sections([normal, touching_inside_out], section_count=5)
    assert any("shared edges" in warning for warning in inside_out.warnings)
    apart = sections([normal, apart_inside_out], section_count=5)
    assert not any("shared edges" in warning for warning in apart.warnings)


def test_open_mesh_sections_are_flagged() -> None:
    result = sections(
        SAMPLES / "open_cube_missing_face" / "open_cube_missing_face_binary.stl",
        section_count=5,
    )

    rows = result.rows()
    assert any(row.open_section for row in rows)
    assert "holes in the mesh" in "; ".join(result.warnings)


def test_mach_plane_sections_of_a_cube(tmp_path: Path) -> None:
    # Mach sqrt(2) gives beta = 1: at theta = 0 the planes are x - y = x0.
    result = sections(_box(tmp_path), section_count=5, mach=math.sqrt(2.0), theta_count=1)
    series = result.series[0]

    assert series.theta_deg == 0.0
    assert series.x == pytest.approx([-0.5, 0.0, 0.5, 1.0, 1.5])
    assert series.area == pytest.approx([0.0, 0.5, 1.0, 0.5, 0.0], abs=1e-12)


def test_every_roll_angle_keeps_the_model_volume(tmp_path: Path) -> None:
    result = sections(_box(tmp_path), section_count=201, mach=1.5, theta_count=8)

    assert len(result.series) == 8
    for series in result.series:
        assert series.volume == pytest.approx(1.0, rel=1e-3)


@pytest.mark.parametrize(("mach", "theta_count"), [(1.0, 1), (1.5, 4)])
def test_sections_are_cut_relative_to_the_flow(
    tmp_path: Path, mach: float, theta_count: int
) -> None:
    alpha, beta = 6.0, -4.0
    axes = wind_axes(alpha, beta)
    assert axes[0] == pytest.approx(
        projection_direction_for_orientation(Orientation(alpha_deg=alpha, beta_deg=beta))
    )
    box = trimesh.creation.box(extents=(3.0, 1.0, 0.5))
    # The same box, turned so that its long axis runs along the flow.
    turned = trimesh.Trimesh(vertices=box.vertices @ axes, faces=box.faces, process=False)
    kwargs = {"section_count": 21, "mach": mach, "theta_count": theta_count}

    along_x = sections(_write_mesh(tmp_path / "box.stl", box), **kwargs)
    along_flow = sections(
        _write_mesh(tmp_path / "turned.stl", turned), alpha_deg=alpha, beta_deg=beta, **kwargs
    )
    misaligned = sections(_write_mesh(tmp_path / "turned.stl", turned), **kwargs)

    for expected, series in zip(along_x.series, along_flow.series, strict=True):
        # STL stores float32 vertices, so the base is normal to the flow only up to
        # roundoff and the last plane no longer catches all of it.
        assert series.x == pytest.approx(expected.x, abs=1e-6)
        assert series.area[:-1] == pytest.approx(expected.area[:-1], abs=1e-6)
    assert misaligned.series[0].length > along_flow.series[0].length
    rows = along_flow.rows()
    assert (rows[0].alpha_deg, rows[0].beta_deg) == (alpha, beta)

    model = inspect_model(tmp_path / "turned.stl")
    loops = section_outline(model, mach=1.0, theta_deg=None, x0=0.5, alpha_deg=alpha, beta_deg=beta)
    points = np.vstack(loops)
    assert points @ axes[0] == pytest.approx(np.full(points.shape[0], 0.5), abs=1e-6)


def test_large_flow_angles_are_calculated_with_a_warning() -> None:
    cube = DATA_DIR / "unit_cube.stl"
    assert not any(
        "off the X axis" in warning for warning in sections(cube, alpha_deg=15.0).warnings
    )

    # Flow straight up: the cube is cut along Z and the sections stay unit squares.
    result = sections(cube, section_count=5, alpha_deg=90.0)
    assert result.series[0].area[1:] == pytest.approx(np.ones(4))
    assert "more than 15° off the X axis" in result.warnings[0]


def test_sears_haack_body_matches_the_minimum_drag() -> None:
    length, radius = 10.0, 0.5
    x = np.linspace(0.0, length, 401)
    profile = radius * (4.0 * (x / length) * (1.0 - x / length)) ** 0.75
    mesh = trimesh.creation.revolve(np.column_stack((profile, x)), sections=128)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    result = calculate_sections(_model_from_mesh(mesh))

    series = result.series[0]
    expected = sears_haack_drag_area(length=series.length, volume=series.volume)
    assert result.wave_drag_area == pytest.approx(expected, rel=1e-3)
    assert series.area == pytest.approx(series.sears_haack_area, abs=2e-3)
    assert result.warnings == ()


def _model_from_mesh(mesh: object):
    from cadmetrics.types import ModelData

    return ModelData(
        path=Path("mesh.stl"),
        source_format="stl",
        vertices=np.asarray(mesh.vertices, dtype=float),  # type: ignore[attr-defined]
        faces=np.asarray(mesh.faces, dtype=np.int64),  # type: ignore[attr-defined]
        input_unit="m",
        output_unit="m",
        volume=None,
        surface_area=None,
        base_area=None,
        is_watertight=True,
    )


def test_wave_drag_of_analytic_distributions() -> None:
    length, max_area = 4.0, 0.3
    x = np.linspace(0.0, length, 101)
    sears_haack = max_area * (4.0 * (x / length) * (1.0 - x / length)) ** 1.5
    volume = 3.0 * math.pi * max_area * length / 16.0

    assert wave_drag_area(x, sears_haack) == pytest.approx(
        9.0 * math.pi * max_area**2 / (2.0 * length**2)
    )
    assert sears_haack_drag_area(length=length, volume=volume) == pytest.approx(
        9.0 * math.pi * max_area**2 / (2.0 * length**2)
    )
    assert sears_haack_area(x, volume=volume) == pytest.approx(sears_haack)
    # The Sears-Haack slope is the single sine term (3 S_max / L) sin(2 phi), which the
    # fitted series reproduces exactly.
    phi = np.arccos(1.0 - 2.0 * x / length)
    slope = 3.0 * max_area / length * np.sin(2.0 * phi)
    assert sears_haack_area_slope(x, volume=volume) == pytest.approx(slope)
    assert fitted_area_slope(x, sears_haack) == pytest.approx(slope, abs=1e-12)
    # All of its wave drag is in the second term.
    spectrum = wave_drag_spectrum(x, sears_haack)
    assert spectrum is not None
    assert spectrum[1] == pytest.approx(wave_drag_area(x, sears_haack))
    assert np.delete(spectrum, 1) == pytest.approx(0.0, abs=1e-12)

    # The von Karman ogive is the minimum-drag nose for a given base area.
    base_area = 0.5
    ogive = base_area / math.pi * (phi - np.sin(2.0 * phi) / 2.0)
    assert wave_drag_area(x, ogive) == pytest.approx(4.0 * base_area**2 / (math.pi * length**2))


def test_section_outline_is_drawn_on_the_cutting_plane() -> None:
    pytest.importorskip("OCP")
    model = inspect_model(SAMPLES / "cylinder_x_r1_l2" / "cylinder_x_r1_l2.step")

    loops = section_outline(model, mach=1.0, theta_deg=None, x0=1.0)
    assert len(loops) == 1
    assert loops[0][:, 0] == pytest.approx(np.ones(loops[0].shape[0]))
    assert np.hypot(loops[0][:, 1], loops[0][:, 2]) == pytest.approx(
        np.ones(loops[0].shape[0]), abs=0.01
    )

    oblique = section_outline(model, mach=math.sqrt(2.0), theta_deg=0.0, x0=1.0)
    points = np.vstack(oblique)
    assert points[:, 0] - points[:, 1] == pytest.approx(np.ones(points.shape[0]))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"section_count": 2}, "sections"),
        ({"mach": 0.8}, "Mach"),
        ({"mach": 1.5, "theta_count": 0}, "theta"),
        ({"mach": 1.5, "theta_count": 7, "symmetric": True}, "even"),
        ({"alpha_deg": float("inf")}, "alpha"),
        ({"beta_deg": float("nan")}, "beta"),
        ({"mach": 1.5, "theta_count": 8, "symmetric": True, "beta_deg": 2.0}, "beta must be 0"),
    ],
)
def test_invalid_section_options_are_rejected(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        sections(DATA_DIR / "unit_cube.stl", **kwargs)  # type: ignore[arg-type]


def test_sections_cli_writes_csv_and_summary(tmp_path: Path) -> None:
    output = tmp_path / "sections.csv"
    result = CliRunner().invoke(
        app,
        [
            "sections",
            str(_box(tmp_path)),
            "--sections",
            "11",
            "--mach",
            "1.5",
            "--thetas",
            "4",
            "--symmetric",
            "--alpha",
            "3",
            "--out",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    rows = list(csv.DictReader(output.read_text(encoding="utf-8").splitlines()))
    # Four roll angles, symmetric: -90, 0, and 90 remain.
    assert len(rows) == 33
    assert {row["theta_deg"] for row in rows} == {"-90.0", "0.0", "90.0"}
    assert {(row["alpha_deg"], row["beta_deg"]) for row in rows} == {("3.0", "0.0")}
    assert float(rows[5]["area"]) > 0.0
    assert rows[0]["mean_wave_drag_area"]
    assert "Section Summary" in result.output


def test_sections_cli_rejects_subsonic_mach() -> None:
    result = CliRunner().invoke(app, ["sections", str(DATA_DIR / "unit_cube.stl"), "--mach", "0.9"])

    assert result.exit_code == 2
    assert "Mach" in result.output
