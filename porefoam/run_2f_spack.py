#!/usr/bin/env python3
"""Spack beadpack two-phase runner (Phase 2).

Direct replacement for src/porefoam2f/script/AllRunImageTwoPhase_spack.

Wires foam.geo.spack (geometry, no solver-policy knowledge) with
porefoam2f_cli (fvSolution/controlDict policy + simulation sweep) and
TwoPhaseCaseRunner to:
1. Sweep geometry params → create/mesh one mesh directory
2. Sweep simulation params → create/run simulation cases

Usage:
    python -m pnmkit.porefoam.run_pf2f_spack \
        --RSpheres "20" \\
        --cementPCents "20" \\
        --ScaleYs "1" \\
        --ScaleZs "1" \\
        --UD1s "200" \\
        --UD0s "10" \\
        --theta0s "150" \\
        --oilFilldFracs "0.1" \\
        --RefineLevels "12" \\
        --nProc 24
"""

import argparse
from pathlib import Path

from .. import runtime as rt
from ..foam.geo import spack as geo
from . import TwoPhaseCaseRunner
from .porefoam2f_cli import add_common_runner_args, add_numerics_args, build_numerics_edits, run_simulation_sweep


def get_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run spack beadpack two-phase simulations (replaces AllRunImageTwoPhase_spack).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_common_runner_args(p)
    geo.add_geometry_args(p)
    add_numerics_args(p)
    return p


def run_spack(argv: list[str] | None = None) -> None:
    args = get_parser().parse_args(argv)

    data_file = "spack"
    work_dir = Path(args.work_dir).resolve()

    geometry = geo.build_geometry(args)
    runner = TwoPhaseCaseRunner(
        template_dir=args.template_dir,
        geometry_builder=geometry,
        work_dir=work_dir,
        extra_template_dir=args.extra_dir,
        inlet="Left",
        outlet="Right",
        vxl_size=args.vxlSize,
    )

    numerics_edits = build_numerics_edits(args)

    for geometry_params in geo.geometry_param_grid(args):
        rt.disp(f"Geometry params: {geometry_params}")

        mesh_case = runner.setup_mesh(
            data_file=data_file,
            geometry_params=geometry_params,
            mesh_tag=args.meshTag,
            numerics_edits=numerics_edits,
        )

        run_simulation_sweep(runner, mesh_case, args)

    rt.disp("Done")


if __name__ == "__main__":
    run_spack()
