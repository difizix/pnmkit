"""Test suites and standalone benchmark runners for pnmkit.foam.

Provides standalone simulation runners, synthetic mesh/geometry generators,
and post-processing verification utilities that can be imported directly by
external benchmarks, test suites, or analysis scripts.
"""

from __future__ import annotations

from pnmkit.porefoam.tests.porefoam1f import run_porefoam1f
from pnmkit.porefoam.tests.post_process import check_avg, extract_summary
from pnmkit.porefoam.tests.voxcylCFMesh import run_voxcyl_cfmesh
from pnmkit.porefoam.tests.voxcylCFMeshFSF import run_voxcyl_cfmesh_fsf
from pnmkit.porefoam.tests.voxcylinder import run_voxcylinder
from pnmkit.porefoam.tests.voxcylinderFSF import run_voxcylinder_fsf
from pnmkit.porefoam.tests.voxyl import create_cylinder

__all__ = [
    "check_avg",
    "create_cylinder",
    "extract_summary",
    "run_porefoam1f",
    "run_voxcyl_cfmesh",
    "run_voxcyl_cfmesh_fsf",
    "run_voxcylinder",
    "run_voxcylinder_fsf",
]
