"""Spack synthetic beadpack geometry: OpenSCAD -> cfMesh.

No porefoam-solver-specific logic: only touches system/meshingDict and
system/meshDict (mesh generation), never fvSolution/controlDict (solver
policy) — which is why this lives in foam/ rather than porefoam/.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ... import runtime as rt
from ..foam_case import FoamCase, MeshBuildResult
from ..foam_mesh import _scad_to_cfmesh
from ..foam_sweep import expand_param_grid, parse_list


class SpackGeometry:
    """Geometry builder for the 'spack' synthetic beadpack.

    Uses OpenSCAD (dataFile.scad) → cfMesh (cartesianMesh) two-pass workflow,
    exactly as in AllRunImageTwoPhase_spack:164-223. Shared helper: _scad_to_cfmesh().
    """

    def __init__(
        self,
        scad_file: str = "spack.scad",
        template_extra_dir: str | None = None,
    ) -> None:
        self.scad_file = scad_file
        self.template_extra_dir = Path(template_extra_dir) if template_extra_dir else None

    def build(self, case: FoamCase, params: dict[str, Any]) -> MeshBuildResult:
        """Build mesh from spack.scad via cfMesh.

        Expected params:
        - RSphere, cementPCent, ScaleY, ScaleZ: substituted into .scad file
        - RefineLevel: controls maxCellSize (30/8/RefineLevel)
        - smoothing_rounds: number of smoothFMesh passes (default 7)
        - two_pass: whether to use two-pass cfMesh (default True)
        - n_layers: prism layers (default 2)
        """
        scad_params = {}
        for key in ("RSphere", "cementPCent", "ScaleY", "ScaleZ"):
            if key in params:
                scad_params[key] = params[key]

        # Copy scad template if available.
        if self.template_extra_dir and (self.template_extra_dir / "scad" / self.scad_file).exists():
            rt.run_sh(
                str(case.case_dir),
                f"cp {self.template_extra_dir / 'scad' / self.scad_file} {case.case_dir}",
            )

        # Substitute BASENAME placeholder in meshingDict (matches bash setValues BASENAME "$mshDir").
        meshing_dict = case.case_dir / "system" / "meshingDict"
        if meshing_dict.exists():
            content = meshing_dict.read_text()
            if "BASENAME" in content:
                meshing_dict.write_text(content.replace("BASENAME", case.case_dir.name))

        return _scad_to_cfmesh(
            case=case,
            scad_file=self.scad_file,
            scad_params=scad_params,
            refine_level=params.get("RefineLevel", 12),
            n_layers=params.get("n_layers", 2),
            two_pass=params.get("two_pass", True),
            smoothing_rounds=params.get("smoothing_rounds", 7),
        )


def add_geometry_args(parser: argparse.ArgumentParser) -> None:
    """Add spack geometry-sweep CLI args (no fvSolution/controlDict keys here)."""
    parser.add_argument("--RSpheres", type=str, default="20", help="RSphere values (space-separated).")
    parser.add_argument("--cementPCents", type=str, default="20", help="cementPCent values (space-separated).")
    parser.add_argument("--ScaleYs", type=str, default="1", help="ScaleY values (space-separated).")
    parser.add_argument("--ScaleZs", type=str, default="1", help="ScaleZ values (space-separated).")
    parser.add_argument("--RefineLevels", type=str, default="12", help="RefineLevel values (space-separated).")
    parser.add_argument("--scad-file", type=str, default="spack.scad", help="OpenSCAD file name.")
    parser.add_argument("--smoothing-rounds", type=int, default=7, help="smoothFMesh rounds.")
    parser.add_argument("--two-pass", action="store_true", default=True, help="Two-pass cfMesh.")
    parser.add_argument("--no-two-pass", dest="two_pass", action="store_false", help="One-pass cfMesh.")
    parser.add_argument("--n-layers", type=int, default=2, help="cfMesh prism layers.")


def build_geometry(args: argparse.Namespace) -> SpackGeometry:
    return SpackGeometry(scad_file=args.scad_file, template_extra_dir=args.extra_dir)


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
