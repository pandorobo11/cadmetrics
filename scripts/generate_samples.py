from __future__ import annotations

import json
from dataclasses import dataclass
from math import pi
from pathlib import Path
from typing import Callable

import numpy as np
import trimesh
from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopoDS import TopoDS_Compound
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from trimesh.exchange.stl import export_stl, export_stl_ascii
from trimesh.transformations import rotation_matrix


ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = ROOT / "samples"
STEP_MM_PER_M = 1000.0


@dataclass(frozen=True)
class SampleSpec:
    name: str
    description: str
    expected: dict[str, float | bool | None]
    stl_factory: Callable[[], trimesh.Trimesh]
    step_factory: Callable[[], object] | None


def main() -> None:
    SAMPLES_DIR.mkdir(exist_ok=True)
    metadata: dict[str, object] = {
        "unit": "m",
        "projection_default": "orthographic along +X onto YZ",
        "samples": {},
    }

    for spec in sample_specs():
        sample_dir = SAMPLES_DIR / spec.name
        sample_dir.mkdir(exist_ok=True)

        mesh = spec.stl_factory()
        mesh.remove_unreferenced_vertices()
        write_stl_files(
            mesh, sample_dir / f"{spec.name}_ascii.stl", sample_dir / f"{spec.name}_binary.stl"
        )

        files = {
            "ascii_stl": str((sample_dir / f"{spec.name}_ascii.stl").relative_to(ROOT)),
            "binary_stl": str((sample_dir / f"{spec.name}_binary.stl").relative_to(ROOT)),
            "step": None,
        }
        if spec.step_factory is not None:
            step_path = sample_dir / f"{spec.name}.step"
            write_step(spec.step_factory(), step_path)
            files["step"] = str(step_path.relative_to(ROOT))

        metadata["samples"][spec.name] = {
            "description": spec.description,
            "expected": spec.expected,
            "files": files,
        }

    add_multi_file_step_component_filter_sample(metadata)
    add_satellite_metadata(metadata)

    (SAMPLES_DIR / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sample_specs() -> list[SampleSpec]:
    return [
        SampleSpec(
            name="unit_cube",
            description="Closed 1 x 1 x 1 cube.",
            expected={
                "volume": 1.0,
                "surface_area": 6.0,
                "base_area": 1.0,
                "projected_area_x": 1.0,
                "is_watertight": True,
            },
            stl_factory=lambda: box_mesh((1.0, 1.0, 1.0)),
            step_factory=lambda: make_box_shape_m(0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
        ),
        SampleSpec(
            name="box_1x2x3",
            description="Closed 1 x 2 x 3 rectangular box.",
            expected={
                "volume": 6.0,
                "surface_area": 22.0,
                "base_area": 6.0,
                "projected_area_x": 6.0,
                "projected_area_y": 3.0,
                "projected_area_z": 2.0,
                "is_watertight": True,
            },
            stl_factory=lambda: box_mesh((1.0, 2.0, 3.0)),
            step_factory=lambda: make_box_shape_m(0.0, 0.0, 0.0, 1.0, 2.0, 3.0),
        ),
        SampleSpec(
            name="sphere_r1",
            description="Closed sphere with radius 1.",
            expected={
                "volume": 4.0 * pi / 3.0,
                "surface_area": 4.0 * pi,
                "base_area": 0.0,
                "projected_area_x": pi,
                "is_watertight": True,
            },
            stl_factory=lambda: trimesh.creation.icosphere(subdivisions=4, radius=1.0),
            step_factory=lambda: BRepPrimAPI_MakeSphere(
                gp_Pnt(0.0, 0.0, 0.0),
                1.0 * STEP_MM_PER_M,
            ).Shape(),
        ),
        SampleSpec(
            name="cylinder_x_r1_l2",
            description="Closed cylinder with radius 1 and length 2 along X.",
            expected={
                "volume": 2.0 * pi,
                "surface_area": 6.0 * pi,
                "base_area": pi,
                "projected_area_x": pi,
                "projected_area_y": 4.0,
                "projected_area_z": 4.0,
                "is_watertight": True,
            },
            stl_factory=cylinder_x_mesh,
            step_factory=lambda: BRepPrimAPI_MakeCylinder(
                gp_Ax2(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(1.0, 0.0, 0.0)),
                1.0 * STEP_MM_PER_M,
                2.0 * STEP_MM_PER_M,
            ).Shape(),
        ),
        SampleSpec(
            name="two_boxes_overlap_projection",
            description="Two separate unit cubes offset along X so their +X projections overlap.",
            expected={
                "volume": 2.0,
                "surface_area": 12.0,
                "base_area": 1.0,
                "projected_area_x": 1.0,
                "is_watertight": True,
            },
            stl_factory=two_boxes_overlap_mesh,
            step_factory=two_boxes_overlap_shape,
        ),
        SampleSpec(
            name="two_boxes_intersecting",
            description="Two unit cubes intersecting by 0.5 along X.",
            expected={
                "volume_stl": 2.0,
                "surface_area_stl": 12.0,
                "base_area_stl": 1.0,
                "volume_step": 1.5,
                "surface_area_step": 8.0,
                "base_area_step": 1.0,
                "projected_area_x": 1.0,
                "is_watertight": True,
            },
            stl_factory=two_boxes_intersecting_mesh,
            step_factory=two_boxes_intersecting_shape,
        ),
        SampleSpec(
            name="open_cube_missing_face",
            description="1 x 1 x 1 cube STL with the +Z face removed.",
            expected={
                "volume": None,
                "surface_area": 5.0,
                "base_area": 1.0,
                "projected_area_x": 1.0,
                "is_watertight": False,
            },
            stl_factory=open_cube_mesh,
            step_factory=None,
        ),
        SampleSpec(
            name="frame_with_hole",
            description="3 x 3 x 0.1 rectangular frame with a centered 1 x 1 through-hole.",
            expected={
                "volume": 0.8,
                "surface_area": 17.6,
                "base_area": 0.3,
                "projected_area_x": 0.3,
                "projected_area_z": 8.0,
                "is_watertight": True,
            },
            stl_factory=frame_with_hole_mesh,
            step_factory=frame_with_hole_shape,
        ),
    ]


def write_stl_files(mesh: trimesh.Trimesh, ascii_path: Path, binary_path: Path) -> None:
    ascii_path.write_text(export_stl_ascii(mesh), encoding="utf-8")
    binary_path.write_bytes(export_stl(mesh))


def write_step(shape: object, path: Path) -> None:
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"Could not write STEP file: {path}")


def make_box_shape(x: float, y: float, z: float, dx: float, dy: float, dz: float) -> object:
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape()


def make_box_shape_m(x: float, y: float, z: float, dx: float, dy: float, dz: float) -> object:
    scale = STEP_MM_PER_M
    return make_box_shape(x * scale, y * scale, z * scale, dx * scale, dy * scale, dz * scale)


def box_mesh(extents: tuple[float, float, float]) -> trimesh.Trimesh:
    return trimesh.creation.box(extents=extents)


def cylinder_x_mesh() -> trimesh.Trimesh:
    mesh = trimesh.creation.cylinder(radius=1.0, height=2.0, sections=192)
    mesh.apply_transform(rotation_matrix(pi / 2.0, [0.0, 1.0, 0.0]))
    return mesh


def two_boxes_overlap_mesh() -> trimesh.Trimesh:
    first = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    second = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    first.apply_translation((-1.0, 0.0, 0.0))
    second.apply_translation((1.0, 0.0, 0.0))
    return trimesh.util.concatenate([first, second])


def two_boxes_overlap_shape() -> object:
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    builder.Add(compound, make_box_shape_m(-1.5, -0.5, -0.5, 1.0, 1.0, 1.0))
    builder.Add(compound, make_box_shape_m(0.5, -0.5, -0.5, 1.0, 1.0, 1.0))
    return compound


def two_boxes_intersecting_mesh() -> trimesh.Trimesh:
    first = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    second = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    first.apply_translation((0.0, 0.0, 0.0))
    second.apply_translation((0.5, 0.0, 0.0))
    return trimesh.util.concatenate([first, second])


def two_boxes_intersecting_shape() -> object:
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    builder.Add(compound, make_box_shape_m(-0.5, -0.5, -0.5, 1.0, 1.0, 1.0))
    builder.Add(compound, make_box_shape_m(0.0, -0.5, -0.5, 1.0, 1.0, 1.0))
    return compound


def open_cube_mesh() -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    keep = mesh.triangles_center[:, 2] < 0.49
    return trimesh.Trimesh(
        vertices=mesh.vertices.copy(), faces=mesh.faces[keep].copy(), process=False
    )


def frame_with_hole_shape() -> object:
    outer = make_box_shape_m(-1.5, -1.5, -0.05, 3.0, 3.0, 0.1)
    cutter = make_box_shape_m(-0.5, -0.5, -0.15, 1.0, 1.0, 0.3)
    cut = BRepAlgoAPI_Cut(outer, cutter)
    cut.Build()
    if not cut.IsDone():
        raise RuntimeError("Could not cut frame-with-hole shape")
    return cut.Shape()


def frame_with_hole_mesh() -> trimesh.Trimesh:
    z_bottom = -0.05
    z_top = 0.05
    vertices: list[tuple[float, float, float]] = []
    index: dict[tuple[float, float, float], int] = {}
    faces: list[tuple[int, int, int]] = []

    def vertex(point: tuple[float, float, float]) -> int:
        if point not in index:
            index[point] = len(vertices)
            vertices.append(point)
        return index[point]

    def quad(points: list[tuple[float, float, float]]) -> None:
        a, b, c, d = [vertex(point) for point in points]
        faces.append((a, b, c))
        faces.append((a, c, d))

    grid = [-1.5, -0.5, 0.5, 1.5]
    occupied = {(x_index, y_index) for x_index in range(3) for y_index in range(3)}
    occupied.remove((1, 1))

    for x_index in range(3):
        for y_index in range(3):
            if (x_index, y_index) not in occupied:
                continue
            x0 = grid[x_index]
            x1 = grid[x_index + 1]
            y0 = grid[y_index]
            y1 = grid[y_index + 1]
            cell = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            quad([(x, y, z_top) for x, y in cell])
            quad([(x, y, z_bottom) for x, y in reversed(cell)])

            if (x_index - 1, y_index) not in occupied:
                quad(
                    [
                        (x0, y0, z_top),
                        (x0, y1, z_top),
                        (x0, y1, z_bottom),
                        (x0, y0, z_bottom),
                    ]
                )
            if (x_index + 1, y_index) not in occupied:
                quad(
                    [
                        (x1, y1, z_top),
                        (x1, y0, z_top),
                        (x1, y0, z_bottom),
                        (x1, y1, z_bottom),
                    ]
                )
            if (x_index, y_index - 1) not in occupied:
                quad(
                    [
                        (x1, y0, z_top),
                        (x0, y0, z_top),
                        (x0, y0, z_bottom),
                        (x1, y0, z_bottom),
                    ]
                )
            if (x_index, y_index + 1) not in occupied:
                quad(
                    [
                        (x0, y1, z_top),
                        (x1, y1, z_top),
                        (x1, y1, z_bottom),
                        (x0, y1, z_bottom),
                    ]
                )

    mesh = trimesh.Trimesh(vertices=np.asarray(vertices), faces=np.asarray(faces), process=False)
    mesh.merge_vertices()
    return mesh


def add_multi_file_step_component_filter_sample(metadata: dict[str, object]) -> None:
    sample_name = "multi_file_step_components"
    sample_dir = SAMPLES_DIR / sample_name
    sample_dir.mkdir(exist_ok=True)
    box_pair_a_path = sample_dir / "box_pair_a.step"
    box_pair_b_path = sample_dir / "box_pair_b.step"
    write_step(
        step_compound(
            [
                make_box_shape_m(0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
                make_box_shape_m(0.0, 2.0, 0.0, 1.0, 1.0, 1.0),
            ]
        ),
        box_pair_a_path,
    )
    write_step(
        step_compound(
            [
                make_box_shape_m(0.0, 4.0, 0.0, 1.0, 1.0, 1.0),
                make_box_shape_m(0.0, 6.0, 0.0, 1.0, 1.0, 1.0),
            ]
        ),
        box_pair_b_path,
    )
    metadata["samples"][sample_name] = {
        "description": "Two STEP files with two unit-cube components each for GUI multi-file filtering.",
        "expected": {
            "component_count": 4,
            "selected_components": [2, 3],
            "selected_volume": 2.0,
            "selected_surface_area": 12.0,
            "selected_base_area": 2.0,
            "selected_projected_area_x": 2.0,
            "volume": 4.0,
            "surface_area": 24.0,
            "base_area": 4.0,
            "projected_area_x": 4.0,
            "is_watertight": True,
        },
        "files": {
            "ascii_stl": None,
            "binary_stl": None,
            "step": None,
            "box_pair_a_step": str(box_pair_a_path.relative_to(ROOT)),
            "box_pair_b_step": str(box_pair_b_path.relative_to(ROOT)),
        },
    }


def step_compound(shapes: list[object]) -> object:
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound


def add_satellite_metadata(metadata: dict[str, object]) -> None:
    satellite_path = SAMPLES_DIR / "satellite" / "satellite.step"
    if not satellite_path.exists():
        return

    metadata["samples"]["satellite"] = {
        "description": "Manual Fusion 360 validation model.",
        "expected": {
            "volume": 2.561328923008496,
            "surface_area": 11.680313693153769,
            "projected_area_x": 0.7852367025156864,
            "projected_area_alpha_60": 3.1799412015662096,
            "is_watertight": True,
        },
        "files": {
            "ascii_stl": None,
            "binary_stl": None,
            "step": str(satellite_path.relative_to(ROOT)),
        },
    }


if __name__ == "__main__":
    main()
