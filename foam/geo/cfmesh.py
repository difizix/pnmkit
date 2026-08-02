"""Voxel image -> STL (image3kit) -> cfMesh geometry (AllRunImageTwoPhaseCFMesh).

No porefoam-solver-specific logic: only touches system/meshDict.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

from ..foam_case import FoamCase, MeshBuildResult
from ..foam_dict import FileKV
from ..foam_mesh import VoxelSurfaceBuilder
from ..foam_sweep import parse_list


class CFMeshGeometry:
    """Geometry builder: voxel image → STL (image3kit) → cfMesh.

    Used by AllRunImageTwoPhaseCFMesh.
    """

    def __init__(self, surface_tool: str = "image3kit") -> None:
        self.surface_tool = surface_tool

    def build(self, case: FoamCase, params: dict[str, Any]) -> MeshBuildResult:
        """Build mesh via voxel→STL→cfMesh.

        Expected params:
        - image: optional image3kit.VxlImgU8
        - data_file: base name (default: 'voxyl')
        - RefineLevel: float (default: 0.90)
        - nLayers: int (default: 2)
        """
        data_file = params.get("data_file", "voxyl")
        refine_level = params.get("RefineLevel", 0.90)
        n_layers = params.get("nLayers", 2)

        # 1-2. voxel -> obj -> solidwalls.stl (shared with VoxelImageGeometry's
        # voxel handling, no porefoam-specific logic).
        VoxelSurfaceBuilder(data_file).build_surface(case, params)

        # 3. Setup meshDict. This is a distinct one-shot cfMesh invocation
        # (copies rather than moves its template, single cartesianMesh call
        # with a custom log name, no checkMesh/smoothing) — kept separate from
        # foam.foam_mesh.CfMeshBackend's two-pass/single-pass patterns rather
        # than forced into that shape.
        cfmesh_dict = case.case_dir / "system" / "meshDict.cfMesh"
        mesh_dict = case.case_dir / "system" / "meshDict"
        if cfmesh_dict.exists():
            shutil.copy(cfmesh_dict, mesh_dict)
        max_cell = 1.0 / refine_level
        case.edit([
            FileKV("system/meshDict", "maxCellSize", str(max_cell)),
            FileKV("system/meshDict", "nLayers", str(n_layers)),
            FileKV("system/meshDict", "stopAfter", "end"),
        ])

        # 4. cartesianMesh
        case.run_app("cartesianMesh", log_name="log.cartesianMesh-1", skip_if_exists=False)

        # 5. ofMesh2Voxel
        case.run_app("ofMesh2Voxel", log_name="log.ofMesh2Voxel-", skip_if_exists=False)

        return MeshBuildResult(case_dir=case.case_dir)


def add_geometry_args(parser: argparse.ArgumentParser) -> None:
    """Add cfMesh voxel-roundtrip geometry-sweep CLI args (no fvSolution/controlDict keys here)."""
    parser.add_argument("--voxel-image", required=True, help="Input voxel image (.mhd).")
    parser.add_argument("--surface-tool", default="vxlToSurf", help="Tool for voxel→STL conversion.")
    parser.add_argument("--RefineLevels", type=str, default="12", help="RefineLevel values (space-separated).")
    parser.add_argument("--smoothing-rounds", type=int, default=7, help="smoothFMesh rounds.")


def build_geometry(args: argparse.Namespace) -> CFMeshGeometry:
    return CFMeshGeometry(surface_tool=args.surface_tool)


def geometry_param_grid(args: argparse.Namespace):
    for refine_level in parse_list(args.RefineLevels):
        yield {
            "RefineLevel": refine_level,
            "voxel_image": args.voxel_image,
            "smoothing_rounds": args.smoothing_rounds,
        }
