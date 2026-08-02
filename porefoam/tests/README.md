# PNMKit Foam Tests & Benchmark Runners

This directory contains standalone simulation runners, synthetic mesh generators, and verification test suites for `pnmkit.foam` and OpenFOAM/porefoam solvers.

The pnmkit is expected to be used as a submodule, present in ./pnmkit, currently pnmkit.porefoam wrapper assumes the porefoam code are located in ./src/porefoam1f and ./src/porefoam2f, as in github/aliraeini/porescale repo.

The modules are **dual-use**:
1. **Standalone benchmark scripts**: Can be executed directly or imported by third-party / downstream scripts to set up and run simulations.
2. **Pytest test suites**: Compare simulation statistics against reference benchmarks stored in [`ref/`](ref/).

---

## File Structure & Suite Overview

| Standalone Runner | Test Counterpart | Solver / Mesh Method | Reference / Metric |
| :--- | :--- | :--- | :--- |
| `porefoam1f.py` | `test_porefoam1f.py` | `icoNSFoam` / Voxel mesh | Single-phase permeability $K_x \approx 2.444 \times 10^{-12} \text{ m}^2$ |
| `voxcylinder.py` | `test_pf2f_voxcylinder.py` | `interFaceFoam` / Smoothed voxel (`SnpCCF`) | Two-phase $U_o(0) \le 0.0015$, $U_o(1000) \approx 0.0026$ |
| `voxcylinderFSF.py` | `test_pf2f_voxcylinderFSF.py` | `interFaceFoam` / Smoothed voxel + FSF (`SnpFSF`) | Two-phase $U_o(0) \le 0.00012$, $U_o(1000) \approx 0.0026$ |
| `voxcylCFMesh.py` | `test_pf2f_voxcylCFMesh.py` | `interFaceFoam` / cfMesh Cartesian (`CfmCCF`) | Two-phase $U_o(0) \le 0.006$, $U_o(1000) \approx 0.005$ |
| `voxcylCFMeshFSF.py` | `test_pf2f_voxcylCFMeshFSF.py` | `interFaceFoam` / cfMesh Cartesian + FSF (`CfmFSF`) | Two-phase $U_o(0) \le 0.004$, $U_o(1000) \approx 0.04$ |

### Supporting Modules

- [`voxyl.py`](voxyl.py): Generates an $18 \times 24 \times 24$ voxel synthetic cylinder using `image3kit.VxlImgU8`, replacing legacy `voxyl.mhd` files.
- [`post_process.py`](post_process.py): Pure Python parser for `log.interFaceFoam` summaries and tolerance assertions (`check_avg`, `extract_summary`).
- [`test_foam_dict.py`](test_foam_dict.py): Fast unit tests for OpenFOAM dictionary editing without requiring OpenFOAM binaries.
- [`ref/`](ref/): Benchmark reference outputs used for regression assertions.

---

## Running Standalone Scripts

Each runner can be executed directly from the terminal. Outputs are written into `$MS_TEST_DIR` (defaults to `runs/tests/` relative to the parent repository root):

```bash
# Run single-phase flow benchmark
python3 pnmkit/porefoam/tests/porefoam1f.py

# Run two-phase flow benchmarks
python3 pnmkit/porefoam/tests/voxcylinder.py
python3 pnmkit/porefoam/tests/voxcylinderFSF.py
python3 pnmkit/porefoam/tests/voxcylCFMesh.py
python3 pnmkit/porefoam/tests/voxcylCFMeshFSF.py
```

You can also run the test counterparts directly as standalone scripts:

```bash
python3 pnmkit/porefoam/tests/test_porefoam1f.py
python3 pnmkit/porefoam/tests/test_pf2f_voxcylinder.py
python3 pnmkit/porefoam/tests/test_pf2f_voxcylinderFSF.py
python3 pnmkit/porefoam/tests/test_pf2f_voxcylCFMesh.py
python3 pnmkit/porefoam/tests/test_pf2f_voxcylCFMeshFSF.py
```

---

## Running with the Makefile

A dedicated [`Makefile`](Makefile) is provided in this directory to run the test suite into `runs/pytest/pnmkit_porefoam` (parallel to `src/porefoam2f/test2f`'s `runs/tests/test2f`) so outputs can be directly inspected and compared:

```bash
cd pnmkit/porefoam/tests

# Run two-phase regression tests into runs/pytest/pnmkit_porefoam
make test

# Run fast unit tests only
make test-fast

# Run individual standalone simulation runners
make voxcylinder
make voxcylinderFSF
make voxcylCFMesh
make voxcylCFMeshFSF

# Compare generated summary files with reference test2f outputs
make compare
```

---

## Running with Pytest

### 1. Default Run (Fast Unit Tests)
By default, the four slow two-phase simulation tests (`test_pf2f_*`) are marked with `@pytest.mark.regression` and deselected via `addopts = "-m 'not regression'"` in `pyproject.toml`.

To run the fast test suite:

```bash
pytest pnmkit/porefoam/tests/
```

This runs `test_foam_dict.py` and `test_porefoam1f.py` in ~2–3 seconds.

### 2. Running Regression Tests
To run the full two-phase regression simulation suite:

```bash
pytest pnmkit/porefoam/tests/ -m regression
```

Or run a single test module:

```bash
pytest pnmkit/porefoam/tests/test_pf2f_voxcylinder.py -m regression
```

---

## Using in Third-Party Code

The package exports simulation runners and helpers in `pnmkit.porefoam.tests`:

```python
from pathlib import Path
from pnmkit.porefoam.tests import (
    create_cylinder,
    run_porefoam1f,
    run_voxcylinder,
    run_voxcylinder_fsf,
    run_voxcyl_cfmesh,
    run_voxcyl_cfmesh_fsf,
)

# 1. Generate synthetic image
img = create_cylinder()

# 2. Run simulation in a custom working directory
results = run_voxcylinder(work_dir=Path("./my_simulations"))

# 3. Access summary file paths
print("Uo1000 summary:", results["Uo1000"])
print("Uo0 summary:   ", results["Uo0"])
```

---

## Idempotency and Caching

Simulations check whether the target case and complete log file already exist (e.g. `\nEnd\n` in `log.interFaceFoam`). If already run, the case setup and solver steps are skipped, and existing summary files are reused. To force re-running a simulation, remove the case folder in `$MS_TEST_DIR/test2f/` or delete the corresponding `log.*` file.
