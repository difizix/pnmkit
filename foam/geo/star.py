"""Star-shaped pore geometry: OpenSCAD -> cfMesh (same pipeline as spack).

No porefoam-solver-specific logic — see foam/geo/spack.py.
"""

from __future__ import annotations

import argparse
from typing import Any

from ..foam_case import FoamCase, MeshBuildResult
from ..foam_sweep import expand_param_grid, parse_list
from .spack import SpackGeometry


class StarGeometry(SpackGeometry):
    """Star-shaped pore geometry (same meshing pipeline as SpackGeometry).

    Differs only in the .scad file used and potentially one-pass vs two-pass.
    """

    def __init__(
        self,
        scad_file: str = "star.scad",
        template_extra_dir: str | None = None,
        two_pass: bool = True,
        smoothing_rounds: int = 5,
    ) -> None:
        super().__init__(scad_file=scad_file, template_extra_dir=template_extra_dir)
        self._two_pass = two_pass
        self._smoothing_rounds = smoothing_rounds

    def build(self, case: FoamCase, params: dict[str, Any]) -> MeshBuildResult:
        params.setdefault("two_pass", self._two_pass)
        params.setdefault("smoothing_rounds", self._smoothing_rounds)
        return super().build(case, params)


def add_geometry_args(parser: argparse.ArgumentParser) -> None:
    """Add star geometry-sweep CLI args (no fvSolution/controlDict keys here)."""
    parser.add_argument("--RSpheres", type=str, default="20", help="RSphere values (space-separated).")
    parser.add_argument("--cementPCents", type=str, default="20", help="cementPCent values (space-separated).")
    parser.add_argument("--ScaleYs", type=str, default="1", help="ScaleY values (space-separated).")
    parser.add_argument("--ScaleZs", type=str, default="1", help="ScaleZ values (space-separated).")
    parser.add_argument("--RefineLevels", type=str, default="12", help="RefineLevel values (space-separated).")
    parser.add_argument("--scad-file", type=str, default="star.scad", help="OpenSCAD file name.")
    parser.add_argument("--smoothing-rounds", type=int, default=5, help="smoothFMesh rounds.")
    parser.add_argument("--two-pass", action="store_true", default=True, help="Two-pass cfMesh.")
    parser.add_argument("--no-two-pass", dest="two_pass", action="store_false", help="One-pass cfMesh.")
    parser.add_argument("--n-layers", type=int, default=2, help="cfMesh prism layers.")


def build_geometry(args: argparse.Namespace) -> StarGeometry:
    return StarGeometry(scad_file=args.scad_file, template_extra_dir=args.extra_dir)


def geometry_param_grid(args: argparse.Namespace):
    """Yield one geometry_params dict per point in the RSphere/cementPCent/Scale*/RefineLevel grid."""
    for geo_params in expand_param_grid(
        RefineLevel=parse_list(args.RefineLevels),
        cementPCent=parse_list(args.cementPCents),
        RSphere=parse_list(args.RSpheres),
        ScaleY=parse_list(args.ScaleYs),
        ScaleZ=parse_list(args.ScaleZs),
    ):
        yield {
            **geo_params,
            "two_pass": args.two_pass,
            "smoothing_rounds": args.smoothing_rounds,
            "n_layers": args.n_layers,
        }
