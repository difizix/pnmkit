"""Shared porefoam2f CLI scaffolding: case/numerics (solver-policy) args.

Geometry-only args and GeometryBuilder classes live in foam.geo — they never
touch fvSolution/controlDict. Everything here does: these are the
porefoam2f-specific dict keys (cAlpha, theta0, surfaceForceModel, ...) and the
UD1/UD0/theta0/oilFilldFrac simulation sweep, shared verbatim by all six
porefoam2f drivers (base, cfmesh, spack, star, stl, tri).
"""

import argparse
from typing import Any

from .. import runtime as rt
from ..foam.foam_dict import FileKV
from ..foam.foam_sweep import expand_param_grid, parse_list
from .porefoam2f_case import TwoPhaseCaseRunner


def add_common_runner_args(
    parser: argparse.ArgumentParser,
    *,
    template_dir=None,
    extra_dir=None,
) -> None:
    """Add the case-template/output-location args shared by all drivers."""
    if template_dir is None:
        template_dir = str(rt.find_script("porefoam2f/script/base"))
    if extra_dir is None:
        extra_dir = str(rt.find_script("porefoam2f/script/baseExtra"))
    parser.add_argument("--template-dir", type=str, default=template_dir, help="Path to the base case template directory.")
    parser.add_argument("--extra-dir", type=str, default=extra_dir, help="Path to the baseExtra directory.")
    parser.add_argument("--work-dir", type=str, default=".", help="Working directory for output mesh/run cases.")
    parser.add_argument("--meshTag", type=str, default="", help="Optional mesh directory tag.")
    parser.add_argument("--caseTag", type=str, default="", help="Optional run directory tag.")
    parser.add_argument("--vxlSize", type=float, default=5e-6, help="Voxel size in meters (for transformPoints).")


def add_numerics_args(parser: argparse.ArgumentParser) -> None:
    """Add porefoam2f solver-policy CLI args (fvSolution/controlDict + sim sweep + solver)."""
    parser.add_argument("--UD1s", type=str, default="200", help="Darcy velocity for phase 1 (oil), um/s.")
    parser.add_argument("--UD0s", type=str, default="10", help="Darcy velocity for phase 0 (water), um/s.")
    parser.add_argument("--theta0s", type=str, default="150", help="Contact angle theta0 values.")
    parser.add_argument("--oilFilldFracs", type=str, default="0.1", help="Initial oil fraction (or >1 for single-phase).")
    parser.add_argument("--thetaIn", type=float, default=90.0, help="Inlet contact angle.")
    parser.add_argument("--thetaOut", type=float, default=90.0, help="Outlet contact angle.")
    parser.add_argument("--pdMeanValue1", type=float, default=0.0, help="Mean pressure phase 1 at outlet.")
    parser.add_argument("--pdMeanValue2", type=float, default=0.0, help="Mean pressure phase 2 at outlet.")
    parser.add_argument("--VSElml", type=str, default="1", help="VSElml for voxel-image init (used if oilFilldFrac<0).")
    parser.add_argument("--nGrowAlpha", type=str, default="0", help="nGrowAlpha for voxelAlphaFieldToFoam.")
    parser.add_argument("--nProc", type=int, default=24, help="Number of MPI processes.")
    parser.add_argument("--endTime", type=float, default=0.2, help="Simulation end time.")
    parser.add_argument("--surfaceForceModel", type=str, default="CCF")
    parser.add_argument("--pcThicknessFactor", type=float, default=0.1)
    parser.add_argument("--cAlpha", type=float, default=1.0)
    parser.add_argument("--fcCorrectTangent", type=float, default=0.05)
    parser.add_argument("--smoothingKernel", type=int, default=2)
    parser.add_argument("--smoothingRelaxFactor", type=float, default=0.95)
    parser.add_argument("--wallSmoothingKernel", type=int, default=2)
    parser.add_argument("--fcdFilter", type=float, default=0.01)
    parser.add_argument("--maxDeltaT", type=float, default=1e-5)
    parser.add_argument("--maxAlphaCo", type=float, default=30.0)
    parser.add_argument("--solver", type=str, default="interFaceFoam", help="Solver executable.")
    parser.add_argument("--skip-solve", action="store_true", help="Set up cases but do not run solver.")


def build_numerics_edits(args: argparse.Namespace) -> list[FileKV]:
    """fvSolution/controlDict edits applied once when a mesh case is set up."""
    return [
        FileKV("system/fvSolution", "cAlpha", str(args.cAlpha)),
        FileKV("system/fvSolution", "pcThicknessFactor", str(args.pcThicknessFactor)),
        FileKV("system/fvSolution", "surfaceForceModel", args.surfaceForceModel),
        FileKV("system/fvSolution", "fcCorrectTangent", str(args.fcCorrectTangent)),
        FileKV("system/fvSolution", "smoothingKernel", str(args.smoothingKernel)),
        FileKV("system/fvSolution", "smoothingRelaxFactor", str(args.smoothingRelaxFactor)),
        FileKV("system/fvSolution", "wallSmoothingKernel", str(args.wallSmoothingKernel)),
        FileKV("system/fvSolution", "fcdFilter", str(args.fcdFilter)),
        FileKV("system/controlDict", "maxDeltaT", str(args.maxDeltaT)),
        FileKV("system/controlDict", "endTime", str(args.endTime)),
    ]


def build_sim_common(args: argparse.Namespace) -> dict[str, Any]:
    """Simulation params shared by every point in the UD1/UD0/theta0/oilFilldFrac sweep."""
    return {
        "thetaIn": args.thetaIn,
        "thetaOut": args.thetaOut,
        "pdMeanValue1": args.pdMeanValue1,
        "pdMeanValue2": args.pdMeanValue2,
        "VSElml": args.VSElml,
        "nGrowAlpha": args.nGrowAlpha,
        "endTime": args.endTime,
        "maxDeltaT": args.maxDeltaT,
        "maxAlphaCo": args.maxAlphaCo,
        "cAlpha": args.cAlpha,
        "pcThicknessFactor": args.pcThicknessFactor,
        "surfaceForceModel": args.surfaceForceModel,
        "fcCorrectTangent": args.fcCorrectTangent,
        "smoothingKernel": args.smoothingKernel,
        "smoothingRelaxFactor": args.smoothingRelaxFactor,
        "wallSmoothingKernel": args.wallSmoothingKernel,
        "fcdFilter": args.fcdFilter,
        "nProc": args.nProc,
    }


def run_simulation_sweep(runner: TwoPhaseCaseRunner, mesh_case: Any, args: argparse.Namespace) -> None:
    """Sweep UD1/UD0/theta0/oilFilldFrac, setting up and (unless --skip-solve) running each case."""
    sim_common = build_sim_common(args)
    for sim_params in expand_param_grid(
        UD1=parse_list(args.UD1s),
        UD0=parse_list(args.UD0s),
        theta0=parse_list(args.theta0s),
        oilFilldFrac=parse_list(args.oilFilldFracs),
    ):
        params = {**sim_common, **sim_params}
        rt.disp(f"  Simulation params: {params}")
        run_case = runner.setup_run_case(mesh_case=mesh_case, params=params, case_tag=args.caseTag)
        if not args.skip_solve:
            runner.run_simulation(run_case, params, solver=args.solver)
