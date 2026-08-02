"""Externally supplied STL geometry: cartesian2DMesh (AllRunImageTwoPhase_stl).

No porefoam-solver-specific logic: only touches system/meshDict.
"""

from __future__ import annotations

import argparse
from typing import Any

from ..foam_case import FoamCase, MeshBuildResult
from ..foam_dict import FileKV
from ..foam_mesh import ExternalStlSurfaceBuilder, _stl_to_cartesian2d_mesh
from ..foam_sweep import parse_list


class StlGeometry:
    """Geometry builder for externally supplied STL files.

    Uses cartesian2DMesh as in AllRunImageTwoPhase_stl.
    """

    def __init__(self, stl_file: str) -> None:
        self.stl_file = stl_file

    def build(self, case: FoamCase, params: dict[str, Any]) -> MeshBuildResult:
        """Build mesh from an existing STL file via cartesian2DMesh.

        Expected params:
        - stl_path: path to the STL file (absolute or relative to case dir)
        """
        ExternalStlSurfaceBuilder(self.stl_file).build_surface(case, params)
        return _stl_to_cartesian2d_mesh(case, self.stl_file)


def add_geometry_args(parser: argparse.ArgumentParser) -> None:
    """Add STL geometry-sweep CLI args (no fvSolution/controlDict keys here)."""
    parser.add_argument("--stl-file", required=True, help="Path to STL file.")
    parser.add_argument("--RefineLevels", type=str, default="12", help="RefineLevel values (space-separated); mesh is per-STL, this only tags sweeps.")
    parser.add_argument("--maxFirstLayerThickness", type=float, default=None)
    parser.add_argument("--relThicknessTol", type=float, default=None)


def build_geometry(args: argparse.Namespace) -> StlGeometry:
    return StlGeometry(stl_file=args.stl_file)


def geometry_param_grid(args: argparse.Namespace):
    # Mesh is per-STL (no RSphere/cementPCent sweep); still support a
    # RefineLevel sweep for different mesh resolutions.
    for refine_level in parse_list(args.RefineLevels):
        yield {"RefineLevel": refine_level, "stl_path": args.stl_file}


def mesh_dict_edits(args: argparse.Namespace) -> list[FileKV]:
    """Extra system/meshDict edits for STL meshing knobs (geometry-side, not solver policy)."""
    edits = []
    if args.maxFirstLayerThickness is not None:
        edits.append(FileKV("system/meshDict", "maxFirstLayerThickness", str(args.maxFirstLayerThickness)))
    if args.relThicknessTol is not None:
        edits.append(FileKV("system/meshDict", "relThicknessTol", str(args.relThicknessTol)))
    return edits
