#!/usr/bin/env python3
"""Porefoam1f single-phase flow simulation on synthetic cylinder.

Direct replacement for src/porefoam1f/test.py.
Can be run standalone or imported by test_porefoam1f.py.
"""

from __future__ import annotations

import os
from pathlib import Path

import image3kit as ik

from pnmkit.foam.foam_case import FoamCase, MeshBuildResult
from pnmkit.porefoam.porefoam1f_case import SinglePhaseCaseRunner
from pnmkit.runtime import find_script


class VoxelCylinder1fGeometry:
    """Geometry builder generating synthetic cylinder directly via image3kit.to_foam_par()."""

    def __init__(self, n_proc_x: int = 2, n_proc_y: int = 1, n_proc_z: int = 1) -> None:
        self.n_par = ik.int3(n_proc_x, n_proc_y, n_proc_z)

    def build(self, case: FoamCase, _params: dict) -> MeshBuildResult:
        cur = Path.cwd()
        os.chdir(case.case_dir)
        try:
            img = ik.VxlImgU8((20, 20, 20))
            img.replace_range(0, 255, 1)
            img.spacing = ik.dbl3(1, 1, 1)
            img.paint(ik.cylinder((0, 10, 10), (20, 10, 10), 5, 0))
            img.spacing = ik.dbl3(1e-6, 1e-6, 1e-6)
            img.to_foam_par(self.n_par, reset_x0=False, keep_bcs=False)
        finally:
            os.chdir(cur)
        return MeshBuildResult(case_dir=case.case_dir)


def run_porefoam1f(work_dir: Path | str) -> Path:
    """Run single-phase flow simulation on synthetic cylinder and return summary file path."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    template_dir = find_script("porefoam1f/script/base")
    assert template_dir.exists(), f"porefoam1f base case template directory not found: {template_dir}"

    n_proc_x, n_proc_y, n_proc_z = 2, 1, 1
    geo = VoxelCylinder1fGeometry(n_proc_x, n_proc_y, n_proc_z)
    runner = SinglePhaseCaseRunner(
        template_dir=template_dir,
        geometry_builder=geo,
        work_dir=work_dir,
    )

    case_params = {
        "mode": "parallel",
        "nProc": n_proc_x * n_proc_y * n_proc_z,
        "nProcX": n_proc_x,
        "nProcY": n_proc_y,
        "nProcZ": n_proc_z,
        "pressure": 1,
        "direction": "X",
        "endTime": 0.1,
    }

    case = runner.setup_mesh(
        data_file="voxcyl20c1f",
        geometry_params={},
        case_params=case_params,
    )

    runner.run_case(
        case=case,
        params=case_params,
        pressure=1,
        direction="X",
        output_format="raw.gz",
        solver="icoNSFoam",
    )

    summary_file = case.case_dir / "summary_voxcyl20c1f-1-X.txt"
    assert summary_file.exists(), f"Summary file {summary_file} was not generated"
    return summary_file


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    tst_dir = Path(os.environ.get("MS_TEST_DIR", repo_root / "runs" / "tests")) / "pytest1f"
    summary = run_porefoam1f(tst_dir)
    print(f"porefoam1f simulation completed: {summary}")
