"""OpenFOAM case runners and variant drivers (porefoam-specific policy).

Geometry builders (SpackGeometry, StarGeometry, TriGeometry, StlGeometry,
CFMeshGeometry, VoxelImageGeometry) have no porefoam-specific logic — they
live in foam.geo / foam.foam_mesh and are re-exported here for convenience.

Phase 2 (porefoam2f-specific):
- Case runner: TwoPhaseCaseRunner

Phase 5 (porefoam1f-specific):
- Case runner: SinglePhaseCaseRunner
"""

from ..foam.foam_mesh import VoxelImageGeometry
from ..foam.geo import CFMeshGeometry, SpackGeometry, StarGeometry, StlGeometry, TriGeometry
from .porefoam1f_case import SinglePhaseCaseRunner
from .porefoam2f_case import TwoPhaseCaseRunner

__all__ = [
    "CFMeshGeometry",
    "SinglePhaseCaseRunner",
    # Geometry builders.
    "SpackGeometry",
    "StarGeometry",
    "StlGeometry",
    "TriGeometry",
    # Case runners.
    "TwoPhaseCaseRunner",
    "VoxelImageGeometry",
]
