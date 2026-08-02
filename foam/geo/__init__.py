"""Synthetic-geometry / meshing variants with no porefoam-solver-specific logic.

Each submodule here builds a mesh (via OpenSCAD+cfMesh, voxel+cfMesh, or an
external STL) and only ever touches system/meshingDict or system/meshDict —
never fvSolution/controlDict (solver policy), which is what keeps this code
in foam/ rather than porefoam/. VoxelImageGeometry, which meshes straight
from a voxel image with no surface/meshDict step at all, lives one level up
in foam.foam_mesh instead.
"""

from .cfmesh import CFMeshGeometry
from .spack import SpackGeometry
from .star import StarGeometry
from .stl import StlGeometry
from .tri import TriGeometry

__all__ = [
    "CFMeshGeometry",
    "SpackGeometry",
    "StarGeometry",
    "StlGeometry",
    "TriGeometry",
]
