#!/usr/bin/env python3
"""Test porefoam2f two-phase flow simulation with cfMesh (CfmCCF)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pnmkit.porefoam.tests.post_process import check_avg
from pnmkit.porefoam.tests.voxcylCFMesh import run_voxcyl_cfmesh


def run_voxcyl_cfmesh_test(work_dir: Path | str) -> None:
    """Run CfmCCF simulation and verify average Umax against reference."""
    summaries = run_voxcyl_cfmesh(work_dir)
    check_avg(summaries["Uo0"], "Umax", 0.0, 0.008)
    check_avg(summaries["Uo1000"], "Umax", 0.007, 1.2)


@pytest.mark.regression
def test_pf2f_voxcyl_cfmesh(tmp_path: Path) -> None:
    work_dir = Path(os.environ.get("MS_TEST_DIR") or tmp_path) / "pytest2f"
    run_voxcyl_cfmesh_test(work_dir)


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    tst_dir = Path(os.environ.get("MS_TEST_DIR", repo_root / "runs" / "tests")) / "pytest2f"
    run_voxcyl_cfmesh_test(tst_dir)
