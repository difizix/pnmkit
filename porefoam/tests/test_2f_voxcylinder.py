#!/usr/bin/env python3
"""Test porefoam2f two-phase flow simulation with voxel mesh (SnpCCF)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pnmkit.porefoam.tests.post_process import check_avg
from pnmkit.porefoam.tests.voxcylinder import run_voxcylinder


def run_voxcylinder_test(work_dir: Path | str) -> None:
    """Run SnpCCF simulation and verify average Umax against reference."""
    summaries = run_voxcylinder(work_dir)
    check_avg(summaries["Uo0"], "Umax", 0.0, 0.0015)
    check_avg(summaries["Uo1000"], "Umax", 0.0026, 0.1)


@pytest.mark.regression
def test_pf2f_voxcylinder(tmp_path: Path) -> None:
    work_dir = Path(os.environ.get("MS_TEST_DIR") or tmp_path) / "pytest2f"
    run_voxcylinder_test(work_dir)


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    tst_dir = Path(os.environ.get("MS_TEST_DIR", repo_root / "runs" / "tests")) / "pytest2f"
    run_voxcylinder_test(tst_dir)
