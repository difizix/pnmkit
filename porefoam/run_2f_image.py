#!/usr/bin/env python3
"""Base two-phase (porefoam2f) voxel-image runner (Phase 5, item 5).

Direct replacement for src/porefoam2f/script/AllRunImageTwoPhase.
Uses VoxelImageGeometry (voxel→FOAM via voxelToFoam) without STL/cfMesh step

Usage:
    python -m pnmkit.porefoam.run_pf2f_image \\
        --images "sample.mhd" \\
        --UD1s "200" --UD0s "10" --theta0s "150" --oilFilldFracs "0.1" \\
        --nProc 24
"""

import argparse
from pathlib import Path

from .. import runtime as rt
from ..foam.foam_mesh import VoxelImageGeometry
from . import TwoPhaseCaseRunner
from .porefoam2f_cli import add_common_runner_args, add_numerics_args, build_numerics_edits, run_simulation_sweep


def get_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run two-phase voxel-image simulations (replaces AllRunImageTwoPhase).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_common_runner_args(p)
    p.add_argument(
        "--images",
        type=str,
        nargs="+",
        default=["*.mhd"],
        help="Input image files (*.mhd / *.nhdr / *.tif).",
    )
    p.add_argument("--inlet", type=str, default="Left")
    p.add_argument("--outlet", type=str, default="Right")
    p.add_argument("--voxel-commands", type=str, default="", help="Extra commands appended to .mhd.")
    add_numerics_args(p)
    return p


def main(argv: list[str] | None = None) -> None:
    args = get_parser().parse_args(argv)
    work_dir = Path(args.work_dir).resolve()

    # Geometry builder: voxel→FOAM directly (no STL/cfMesh) — shared with porefoam1f.
    geometry = VoxelImageGeometry(parallel=False)

    runner = TwoPhaseCaseRunner(
        template_dir=args.template_dir,
        geometry_builder=geometry,
        work_dir=work_dir,
        extra_template_dir=args.extra_dir if args.extra_dir else None,
        inlet=args.inlet,
        outlet=args.outlet,
        vxl_size=args.vxlSize,
    )

    numerics_edits = build_numerics_edits(args)

    for image_file in args.images:
        data_file = Path(image_file).stem
        rt.disp(f"Processing image: {image_file}")

        mesh_case = runner.setup_mesh(
            data_file=data_file,
            geometry_params={
                "mhd_file": f"{data_file}_input.mhd",
                "parallel": False,
            },
            mesh_tag=args.meshTag,
            numerics_edits=numerics_edits,
        )

        run_simulation_sweep(runner, mesh_case, args)

        rt.disp(f"____________________________ end: {data_file} ____________________________")


if __name__ == "__main__":
    main()
