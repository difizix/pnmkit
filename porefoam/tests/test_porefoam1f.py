#!/usr/bin/env python3
"""Test porefoam1f single-phase flow simulation using pnmkit.foam and image3kit."""

from __future__ import annotations

import os
from pathlib import Path

from pnmkit.porefoam.tests.porefoam1f import run_porefoam1f
from pnmkit.runtime import read_deviates


def run_porefoam1f_test(work_dir: Path | str) -> int:
    """Run porefoam1f simulation and verify permeability K_x against reference."""
    summary_file = run_porefoam1f(work_dir)
    return read_deviates(str(summary_file), "K_x= ", 2.44436e-12)


def test_porefoam1f(tmp_path: Path) -> None:
    work_dir = Path(os.environ.get("MS_TEST_DIR") or tmp_path) / "pytest1f"
    n_err = run_porefoam1f_test(work_dir)
    assert n_err == 0, "Permeability K_x deviated beyond tolerance"


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    tst_dir = Path(os.environ.get("MS_TEST_DIR", repo_root / "runs" / "tests")) / "pytest1f"
    err = run_porefoam1f_test(tst_dir)
    raise SystemExit(err)
