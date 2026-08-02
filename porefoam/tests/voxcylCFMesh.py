#!/usr/bin/env python3
"""Porefoam2f two-phase flow simulation with cfMesh (CfmCCF).

Direct replacement for src/porefoam2f/test2f/voxcylCFMesh.sh.
Can be run standalone or imported by test_pf2f_voxcylCFMesh.py.
"""

from __future__ import annotations

import os
from pathlib import Path

from pnmkit.foam.foam_dict import FileKV
from pnmkit.foam.geo.cfmesh import CFMeshGeometry
from pnmkit.porefoam.porefoam2f_case import TwoPhaseCaseRunner
from pnmkit.porefoam.tests.post_process import extract_summary
from pnmkit.porefoam.tests.voxyl import create_cylinder
from pnmkit.runtime import find_script


def run_voxcyl_cfmesh(work_dir: Path | str) -> dict[str, Path]:
    """Run CFMesh two-phase cylinder simulation and return summary file paths."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    template_dir = find_script("porefoam2f/script/base")
    assert template_dir.exists(), f"porefoam2f base case template directory not found: {template_dir}"
    extra_dir = find_script("porefoam2f/script/baseExtra")
    if not extra_dir.exists():
        extra_dir = None

    img = create_cylinder()

    mesh_tag = "CfmCCF"
    surface_force_model = "CCF"
    refine_level = 0.90
    max_alpha_co = 15.0
    end_time = 0.003
    n_proc = 4

    geo = CFMeshGeometry()
    runner = TwoPhaseCaseRunner(
        template_dir=template_dir,
        geometry_builder=geo,
        work_dir=work_dir,
        extra_template_dir=extra_dir,
        inlet="Left",
        outlet="Right",
        vxl_size=1e-6,
    )

    geometry_params = {
        "image": img,
        "data_file": "voxyl",
        "RefineLevel": refine_level,
        "smoothMeshNIter": 0,
    }

    numerics_edits = [
        FileKV("system/fvSolution", "surfaceForceModel", surface_force_model),
        FileKV("system/controlDict", "maxAlphaCo", str(max_alpha_co)),
        FileKV("system/controlDict", "endTime", str(end_time)),
    ]

    mesh_case = runner.setup_mesh(
        data_file="voxyl",
        geometry_params=geometry_params,
        mesh_tag=mesh_tag,
        numerics_edits=numerics_edits,
    )

    summaries: dict[str, Path] = {}

    for ud1 in [1000, 0]:
        sim_params = {
            "UD1": ud1,
            "UD0": 10,
            "theta0": 140,
            "thetaIn": 90,
            "thetaOut": 90,
            "oilFilldFrac": 0.4,
            "endTime": end_time,
            "maxDeltaT": 1e-5,
            "maxAlphaCo": max_alpha_co,
            "surfaceForceModel": surface_force_model,
            "nProc": n_proc,
        }

        run_case = runner.setup_run_case(
            mesh_case=mesh_case,
            params=sim_params,
        )

        runner.run_simulation(run_case, sim_params, solver="interFaceFoam")

        log_file = run_case.case_dir / "log.interFaceFoam"
        summary_file = work_dir / f"{run_case.case_dir.name}_summary.txt"
        extract_summary(log_file, summary_file)
        summaries[f"Uo{ud1}"] = summary_file

    return summaries


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    tst_dir = Path(os.environ.get("MS_TEST_DIR", repo_root / "runs" / "tests")) / "pytest2f"
    summaries = run_voxcyl_cfmesh(tst_dir)
    for tag, path in summaries.items():
        print(f"CfmCCF {tag} completed: {path}")
