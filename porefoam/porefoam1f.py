#!/usr/bin/env python3
"""porefoam1f single-phase drivers (Phase 5, item 6).

Provides four driver modes matching the bash scripts:
- serial:     AllRunImage
- parallel:   AllRunImagePar
- distributed: AllRunImageParDistributed
- savememory: AllRunImageParSaveMemory

All use VoxelImageGeometry + SinglePhaseCaseRunner.

Usage:
    python -m pnmkit.porefoam.porefoam1f \\
        --images "*.mhd" \\
        --directions "X Y Z" \\
        --mode serial|parallel|distributed|savememory \\
        --output-format raw.gz
"""

import argparse
from pathlib import Path

from .. import runtime as rt
from ..foam.foam_dict import FileKV
from . import SinglePhaseCaseRunner, VoxelImageGeometry


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run single-phase (porefoam1f) simulations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Input.
    p.add_argument(
        "--images",
        type=str,
        nargs="+",
        default=["*.mhd"],
        help="Input image files (*.mhd / *.nhdr / *.tif / *.am).",
    )
    p.add_argument(
        "--directions",
        type=str,
        nargs="+",
        default=["X"],
        choices=["X", "Y", "Z"],
        help="Flow directions.",
    )
    p.add_argument(
        "--pressures",
        type=float,
        nargs="+",
        default=[1.0],
        help="Pressure drop values (Pa).",
    )

    # Mode.
    p.add_argument(
        "--mode",
        type=str,
        default="serial",
        choices=["serial", "parallel", "distributed", "savememory"],
        help="Run mode: serial, parallel, distributed, or savememory.",
    )

    # Directories.
    p.add_argument(
        "--template-dir",
        type=str,
        default=str(rt.find_script("porefoam1f/script/base")),
        help="Base case template directory.",
    )
    p.add_argument(
        "--work-dir",
        type=str,
        default=".",
        help="Output directory.",
    )

    # MPI settings.
    p.add_argument("--nProcX", type=int, default=None, help="MPI processes in X.")
    p.add_argument("--nProcY", type=int, default=None, help="MPI processes in Y.")
    p.add_argument("--nProcZ", type=int, default=None, help="MPI processes in Z.")
    p.add_argument(
        "--hostfile",
        type=str,
        default=str(rt.find_script("porefoam1f/script/machines.txt")),
        help="Hostfile for distributed runs.",
    )

    # voxelToFoamPar options.
    p.add_argument("--resetX0", type=str, default="False", choices=["True", "False"])
    p.add_argument("--keepBCs", type=str, default="False", choices=["True", "False"])

    # Simulation parameters.
    p.add_argument("--endTime", type=float, default=0.1)
    p.add_argument(
        "--output-format",
        type=str,
        default="raw.gz",
        help="FOAM2Voxel output format.",
    )
    p.add_argument("--tag", type=str, default="", help="Case directory tag.")
    p.add_argument("--case_tag", type=str, default="", help="Additional case suffix.")
    p.add_argument("--voxel-commands", type=str, default="", help="Extra voxelCommands appended to .mhd.")
    p.add_argument("--solver", type=str, default="icoNSFoam", help="NS solver name.")
    p.add_argument("--skip-solve", action="store_true", help="Set up but do not run solver.")
    p.add_argument("--skip-potential", action="store_true", help="Skip iPotentialFoam.")
    p.add_argument(
        "--delete-of-res",
        action="store_true",
        help="Delete processor dirs after run.",
    )

    return p.parse_args(argv)


def get_mode_defaults(mode: str) -> dict:
    """Return default MPI settings per mode, matching bash scripts."""
    if mode == "serial":
        return {"nProcX": 1, "nProcY": 1, "nProcZ": 1}
    if mode == "parallel":
        # AllRunImagePar defaults.
        return {"nProcX": 2, "nProcY": 2, "nProcZ": 2}
    if mode in ("distributed", "savememory"):
        # AllRunImageParDistributed and AllRunImageParSaveMemory defaults.
        return {"nProcX": 4, "nProcY": 4, "nProcZ": 2}
    return {"nProcX": 2, "nProcY": 2, "nProcZ": 2}


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    work_dir = Path(args.work_dir).resolve()
    rt.mkdr(str(work_dir))

    mode = args.mode
    save_memory = mode == "savememory"

    # Default MPI settings.
    mode_defaults = get_mode_defaults(mode)
    n_proc_x = args.nProcX or mode_defaults["nProcX"]
    n_proc_y = args.nProcY or mode_defaults["nProcY"]
    n_proc_z = args.nProcZ or mode_defaults["nProcZ"]
    n_proc = n_proc_x * n_proc_y * n_proc_z

    rt.disp(f"Mode: {mode}")
    rt.disp(f"nProcessors: {n_proc_x} x {n_proc_y} x {n_proc_z} = {n_proc}")

    # Geometry builder.
    is_parallel = mode in ("parallel", "distributed", "savememory")
    geo = VoxelImageGeometry(
        parallel=is_parallel,
        np=n_proc,
    )

    # Case runner.
    runner = SinglePhaseCaseRunner(
        template_dir=args.template_dir,
        geometry_builder=geo,
        work_dir=work_dir,
    )

    # Numerics edits applied after meshing.
    numerics_edits = [
        FileKV("system/fvSolution", "relaxationFactors.U", "0.5"),
        FileKV("system/controlDict", "endTime", str(args.endTime)),
        FileKV("system/controlDict", "writeInterval", "1000"),
    ]

    # Prepare common params dict.
    common_params = {
        "mode": mode,
        "nProc": n_proc,
        "nProcX": n_proc_x,
        "nProcY": n_proc_y,
        "nProcZ": n_proc_z,
        "endTime": args.endTime,
        "tag": args.tag,
        "case_tag": args.case_tag,
        "skip_potential": args.skip_potential,
    }

    if mode == "distributed":
        common_params["hostfile"] = args.hostfile

    # voxelToFoamPar params.
    geo_common = {
        "parallel": is_parallel,
        "np": n_proc,
        "nProcX": n_proc_x,
        "nProcY": n_proc_y,
        "nProcZ": n_proc_z,
        "resetX0": args.resetX0,
        "keepBCs": args.keepBCs,
    }

    # Expand image list.
    import glob

    image_files = []
    for pattern in args.images:
        matches = glob.glob(str(work_dir / pattern))
        if matches:
            image_files.extend(matches)
        else:
            # Assume literal path.
            image_files.append(pattern)

    if not image_files:
        rt.disp(f"No images found for {args.images} in {work_dir}")
        return

    rt.disp(f"Images: {' '.join(image_files)}")
    rt.disp(f"Flow directions: {args.directions}")

    for image_file in image_files:
        # Strip extension(s) to get data_file.
        data_file = Path(image_file).stem
        data_file = data_file.replace(".gz", "")

        # Find actual image file.
        image_path = runner.find_image_file(data_file, work_dir)
        if image_path is None:
            rt.disp(f"Warning: no image file found for {data_file}, skipping.")
            continue

        rt.disp(f"Processing image: {image_path.name} → data_file: {data_file}")

        # Create prefix directory.
        prefix_dir = work_dir / data_file
        rt.mkdr(str(prefix_dir))

        for direction in args.directions:
            rt.disp(f"Flow direction: {direction}")

            for pressure in args.pressures:
                rt.disp(f"Delta p along {direction}: {pressure} Pa")

                case_params = {**common_params, "pressure": pressure, "direction": direction}
                geometry_params = {
                    **geo_common,
                    "mhd_file": f"{data_file}_input.mhd",
                }

                # Build case.
                case = runner.setup_mesh(
                    data_file=data_file,
                    geometry_params=geometry_params,
                    case_params=case_params,
                    numerics_edits=numerics_edits,
                    voxel_commands=args.voxel_commands if args.voxel_commands else None,
                )

                # Prepare .mhd file.
                runner.prepare_mhd_file(case, data_file, image_path, args.voxel_commands or None)

                # Run simulation.
                if not args.skip_solve:
                    runner.run_case(
                        case=case,
                        params=case_params,
                        pressure=pressure,
                        direction=direction,
                        output_format=args.output_format,
                        save_memory=save_memory,
                        solver=args.solver,
                    )

                # Optionally delete processor dirs.
                if args.delete_of_res and case.case_dir.exists():
                    for proc_dir in case.case_dir.glob("processor*"):
                        rt.run_sh(str(case.case_dir), f"rm -r {proc_dir}")

                rt.disp(f"_______ end: {data_file}/{direction}/{pressure} ___________")


if __name__ == "__main__":
    main()
