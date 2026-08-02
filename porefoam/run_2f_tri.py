#!/usr/bin/env python3
"""Triangular pore two-phase runner.

Replacement for src/porefoam2f/script/AllRunImageTwoPhase_tri.
Same structure as spack.py, uses foam.geo.tri instead.
"""

import argparse
from pathlib import Path

from .. import runtime as rt
from ..foam.geo import tri as geo
from . import TwoPhaseCaseRunner
from .porefoam2f_cli import add_common_runner_args, add_numerics_args, build_numerics_edits, run_simulation_sweep


def get_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run triangular pore two-phase simulations.")
    add_common_runner_args(p)
    geo.add_geometry_args(p)
    add_numerics_args(p)
    return p


def main(argv=None):
    args = get_parser().parse_args(argv)
    data_file = "tri"
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
        mesh_case = runner.setup_mesh(
            data_file=data_file,
            geometry_params=geometry_params,
            mesh_tag=args.meshTag,
            numerics_edits=numerics_edits,
        )

        run_simulation_sweep(runner, mesh_case, args)

    rt.disp("Done")


if __name__ == "__main__":
    main()
