"""Generic meshing helpers and GeometryBuilder protocol (Phase 1 — Generic core).

Defines the GeometryBuilder protocol used by CaseTemplateRunner, plus reusable
solver-agnostic meshing helpers starting with _scad_to_cfmesh().

Solver-specific geometry classes (e.g. SpackGeometry, StarGeometry) live in
porefoam/. VoxelImageGeometry lives here instead: it has no porefoam-specific
dict-key logic and is used by both porefoam1f and porefoam2f.
"""

import glob
import os
from pathlib import Path
from typing import Any, Protocol

from . import runtime as rt
from .foam_case import FoamCase, MeshBuildResult
from .foam_dict import FileKV


class GeometryBuilder(Protocol):
    """Protocol for mesh generation strategies.

    Any class implementing this protocol can be passed to CaseTemplateRunner.
    The generic layer knows nothing about which solver or case topology the
    mesh targets — only that build() populates case.constant/polyMesh.

    Example implementations:
    - SpackGeometry: openscad + cfMesh (porefoam2f)
    - VoxelImageGeometry: voxel image → foam mesh (porefoam2f base, porefoam1f)
    - SnappyHexMeshGeometry: STL + snappyHexMesh (future gcfoam)
    """

    def build(self, case: FoamCase, params: dict[str, Any]) -> MeshBuildResult:
        """Generate mesh in the given case directory.

        Args:
            case: FoamCase whose directory receives the mesh.
            params: Geometry-specific parameters.

        Returns:
            MeshBuildResult describing what was generated.
        """
        ...


# ---- surface generation vs. volume-meshing backend ----
#
# Mesh generation splits into two independent axes:
#   - SurfaceBuilder: how to get an STL surface (OpenSCAD, voxel image, external file).
#   - MeshBackend: how to turn that surface into a volume mesh (cfMesh today;
#     snappyHexMesh could be added later as another MeshBackend, reusing every
#     existing SurfaceBuilder for free).
# VoxelImageGeometry (above) is a third, orthogonal path: it meshes straight from
# a voxel image with no STL/surface step, so it doesn't compose with these.


class SurfaceBuilder(Protocol):
    """Protocol for producing an STL surface in a case directory."""

    def build_surface(self, case: FoamCase, params: dict[str, Any]) -> Path:
        """Generate (or stage) an STL surface in case.case_dir.

        Returns:
            Path to the resulting STL file.
        """
        ...


class MeshBackend(Protocol):
    """Protocol for turning a surface STL into a volume mesh."""

    def mesh_surface(self, case: FoamCase, stl_path: Path, params: dict[str, Any]) -> MeshBuildResult:
        """Generate a volume mesh in case.case_dir from the given surface."""
        ...


class ScadSurfaceBuilder:
    """Builds an STL surface from an OpenSCAD file.

    Reproduces the openscad → surfacePointMerge → surfaceAutoPatch steps from
    AllRunImageTwoPhase_spack:164-180, shared by SpackGeometry, StarGeometry,
    and TriGeometry.
    """

    def __init__(self, scad_file: str, stl_name: str = "solidwalls0.stl") -> None:
        self.scad_file = scad_file
        self.stl_name = stl_name

    def build_surface(self, case: FoamCase, params: dict[str, Any]) -> Path:
        """Build solidwalls.stl from self.scad_file.

        Expected params:
        - scad_params: dict of OpenSCAD variable substitutions (e.g. RSphere).
        """
        scad_params = params.get("scad_params") or {}

        # Substitute parameters in the .scad file (sed-like line replacement).
        scad_path = case.case_dir / self.scad_file
        if scad_params and scad_path.exists():
            import re

            text = scad_path.read_text()
            for key, val in scad_params.items():
                # Match OpenSCAD-style assignment: "key = value" on its own line.
                text = re.sub(
                    rf"^\s*{re.escape(key)}\s*=\s*.*$",
                    f"{key} = {val}",
                    text,
                    flags=re.MULTILINE,
                )
            scad_path.write_text(text)

        case.run_app("openscad", ["-o", self.stl_name, self.scad_file])
        case.run_app("surfacePointMerge", [self.stl_name, "0.1", "solidwalls.obj"])
        case.run_app("surfaceAutoPatch", ["solidwalls.obj", "solidwalls.stl", "100"])
        return case.case_dir / "solidwalls.stl"


class VoxelSurfaceBuilder:
    """Builds an STL surface from a voxel image.

    Reproduces the voxel → obj → surfaceAutoPatch steps used by CFMeshGeometry
    (AllRunImageTwoPhaseCFMesh), via image3kit.to_surf_mesh() or vxlToSurf.
    """

    def __init__(self, data_file: str = "voxyl") -> None:
        self.data_file = data_file

    def build_surface(self, case: FoamCase, params: dict[str, Any]) -> Path:
        """Build solidwalls.stl from a voxel image.

        Expected params:
        - image: optional image3kit.VxlImgU8
        - data_file: base name (default: self.data_file)
        - voxel_image: input .mhd file, if `image` is not given
        """
        data_file = params.get("data_file", self.data_file)
        img = params.get("image")
        if img is not None:
            import image3kit as ik

            img_copy = ik.VxlImgU8(img)
            img_copy.spacing = ik.dbl3(1, 1, 1)
            cur = Path.cwd()
            try:
                os.chdir(case.case_dir)
                img_copy.to_surf_mesh(
                    {"extractBoxBoundary": True, "SurfUnitIsVoxel": True},
                    f"{data_file}.obj",
                )
            finally:
                os.chdir(cur)
        else:
            voxel_image = params.get("voxel_image", f"{data_file}_input.mhd")
            case.run_app("vxlToSurf", [voxel_image, f"{data_file}.obj"])

        case.run_app("surfaceAutoPatch", [f"{data_file}0.obj", "solidwalls.stl", "100"])
        return case.case_dir / "solidwalls.stl"


class ExternalStlSurfaceBuilder:
    """Stages an externally supplied STL file into the case directory."""

    def __init__(self, stl_file: str) -> None:
        self.stl_file = stl_file

    def build_surface(self, case: FoamCase, params: dict[str, Any]) -> Path:
        """Copy the STL into case.case_dir if it isn't already there.

        Expected params:
        - stl_path: path to the STL file (absolute or relative to case dir)
        """
        stl_path = params.get("stl_path", self.stl_file)
        dest = case.case_dir / self.stl_file
        if not (case.case_dir / stl_path).exists():
            rt.run_sh(str(case.case_dir), f"cp {stl_path} .")
        return dest


class CfMeshBackend:
    """Turns a surface STL into a volume mesh via cfMesh.

    Covers the cfMesh invocation patterns found across the porefoam2f geometry
    variants — 3D two-pass (patchAssignment, then full mesh) with smoothing,
    3D single-pass with smoothing, and 2D — as configuration rather than
    separate reimplementations. (CFMeshGeometry's own one-shot cartesianMesh
    call, which copies rather than moves its meshDict template and skips
    checkMesh/smoothing, remains its own small variant — see
    foam/geo/cfmesh.py — since folding it in here would require guessing
    at intent behind those differences.)
    """

    def __init__(
        self,
        dimension: int = 3,
        mesh_dict_template: str | None = "meshDict.cfMesh",
        two_pass: bool = True,
        smoothing_rounds: int = 7,
        refine_level: float = 12,
        n_layers: int = 2,
        max_cell_size: float | None = None,
    ) -> None:
        self.dimension = dimension
        self.mesh_dict_template = mesh_dict_template
        self.two_pass = two_pass
        self.smoothing_rounds = smoothing_rounds
        self.refine_level = refine_level
        self.n_layers = n_layers
        self.max_cell_size = max_cell_size

    def mesh_surface(self, case: FoamCase, stl_path: Path, params: dict[str, Any]) -> MeshBuildResult:
        if self.dimension == 2:
            case.run_app("cartesian2DMesh", [stl_path.name])
            case.run_app("checkMesh")
            return MeshBuildResult(case_dir=case.case_dir)

        two_pass = params.get("two_pass", self.two_pass)
        n_layers = params.get("n_layers", self.n_layers)
        smoothing_rounds = params.get("smoothing_rounds", self.smoothing_rounds)
        max_cell_size = params.get("max_cell_size", self.max_cell_size)
        if max_cell_size is None:
            refine_level = params.get("refine_level", self.refine_level)
            max_cell_size = 30.0 / 8.0 / refine_level

        if self.mesh_dict_template and (case.case_dir / "system" / self.mesh_dict_template).exists():
            rt.run_sh(str(case.case_dir), f"mv system/{self.mesh_dict_template} system/meshDict")

        # Pass 1: patchAssignment only.
        case.edit(
            [
                FileKV("system/meshDict", "maxCellSize", str(max_cell_size)),
                FileKV("system/meshDict", "nLayers", str(n_layers)),
                FileKV("system/meshDict", "stopAfter", "patchAssignment"),
                FileKV("system/meshDict", "skipSteps", "0 ()"),
            ]
        )

        if two_pass:
            case.run_app("cartesianMesh")
            case.run_app("combinePatchFaces", ["70"])

            # Move generated mesh to constant/polyMesh.
            # cfMesh writes to a time-like dir (e.g. 1e-07/).
            cfmesh_out = glob.glob(str(case.case_dir / "1e*"))
            if cfmesh_out:
                rt.run_sh(
                    str(case.case_dir),
                    f"cp {cfmesh_out[0]}/polyMesh/* constant/polyMesh/",
                )
                rt.run_sh(
                    str(case.case_dir),
                    f"rm -r {cfmesh_out[0]}",
                )

            # Pass 2: full mesh.
            case.edit(
                [
                    FileKV("system/meshDict", "stopAfter", "end"),
                    FileKV("system/meshDict", "skipSteps", "1 ( templateGeneration )"),
                ]
            )
            case.run_app("cartesianMesh")
            case.run_app("checkMesh")
        else:
            case.run_app("cartesianMesh")
            case.run_app("checkMesh")

        # Smoothing.
        _smooth_mesh(case, smoothing_rounds)

        return MeshBuildResult(case_dir=case.case_dir)


# ---- reusable meshing helpers (thin wrappers over SurfaceBuilder + MeshBackend) ----


def _scad_to_cfmesh(
    case: FoamCase,
    scad_file: str,
    scad_params: dict[str, str | int | float],
    mesh_dict_template: str = "meshDict.cfMesh",
    two_pass: bool = True,
    smoothing_rounds: int = 7,
    refine_level: float = 12,
    n_layers: int = 2,
    max_cell_size: float | None = None,
) -> MeshBuildResult:
    """Generate mesh from an OpenSCAD file via cfMesh (cartesianMesh).

    Composes ScadSurfaceBuilder + CfMeshBackend; kept as a function for the
    existing call sites in SpackGeometry/StarGeometry/TriGeometry.

    Args:
        case: FoamCase directory receiving the mesh.
        scad_file: Name of the .scad file (copied from template already).
        scad_params: Parameters to substitute in the .scad file (e.g. RSphere).
        mesh_dict_template: Template meshDict file name in system/.
        two_pass: If True, run two-pass cfMesh (patchAssignment then full).
        smoothing_rounds: Number of smoothFMesh iterations.
        refine_level: Refinement level for maxCellSize computation.
        n_layers: Number of prism layers in cfMesh.
        max_cell_size: Override computed maxCellSize; if None, uses 30/8/refine_level.

    Returns:
        MeshBuildResult with point/cell/face counts.
    """
    stl_path = ScadSurfaceBuilder(scad_file).build_surface(case, {"scad_params": scad_params})
    backend = CfMeshBackend(
        dimension=3,
        mesh_dict_template=mesh_dict_template,
        two_pass=two_pass,
        smoothing_rounds=smoothing_rounds,
        refine_level=refine_level,
        n_layers=n_layers,
        max_cell_size=max_cell_size,
    )
    return backend.mesh_surface(case, stl_path, {})


def _smooth_mesh(case: FoamCase, rounds: int = 7) -> None:
    """Apply the smoothing sequence from AllRunImageTwoPhase_spack.

    Alternates between layer-preserving and volume-isotropic smoothing,
    running checkMesh periodically.
    """
    # Pattern from spack script: alternating (alpha=0.3 iters=20 layers=2 volIso=1)
    # and (alpha=0.2 iters=20 layers=0 volIso=1) smoothing.
    sequence = [
        (0.3, 20, 2, 1),
        (0.2, 20, 0, 1),
        (0.3, 20, 2, 1),
        (0.2, 20, 0, 1),
        (0.3, 20, 2, 1),
        (0.2, 20, 0, 1),
        (0.3, 20, 0, 1),  # final pass
    ]

    for i, (alpha, iters, layers, vol_iso) in enumerate(sequence):
        if i >= rounds:
            break
        case.smooth_f_mesh(alpha, iters, layers, vol_iso)
        if i % 2 == 1 or i == rounds - 1:
            case.run_app("checkMesh")


def _voxel_to_foam(case: FoamCase, mhd_file: str) -> MeshBuildResult:
    """Generate mesh directly from a voxel image via voxelToFoam.

    Args:
        case: FoamCase directory receiving the mesh.
        mhd_file: Name of the .mhd image file (relative to case dir).

    Returns:
        MeshBuildResult.
    """
    case.run_app("voxelToFoam", [mhd_file])
    return MeshBuildResult(case_dir=case.case_dir)


def _voxel_to_foam_par(case: FoamCase, mhd_file: str, np: int = 8) -> MeshBuildResult:
    """Generate mesh from a voxel image via voxelToFoamPar (decomposed).

    Args:
        case: FoamCase directory receiving the mesh.
        mhd_file: Name of the .mhd image file.
        np: Number of MPI processes.

    Returns:
        MeshBuildResult.
    """
    case.run_mpi("voxelToFoamPar", np, [mhd_file])
    return MeshBuildResult(case_dir=case.case_dir)


class VoxelImageGeometry:
    """Geometry builder: voxel image → foam mesh via image3kit or voxelToFoam/voxelToFoamPar.

    Used by porefoam2f's base AllRunImageTwoPhase and by porefoam1f (meshing straight
    from voxel images with no STL/cfMesh step) — no porefoam-solver-specific logic.
    """

    def __init__(self, parallel: bool = False, np: int = 8) -> None:
        self.parallel = parallel
        self.np = np

    def build(self, case: FoamCase, params: dict[str, Any]) -> MeshBuildResult:
        """Build mesh from a voxel image via image3kit.to_foam (or voxelToFoam).

        Expected params:
        - image: optional image3kit.VxlImgU8
        - mhd_file: name of the .mhd image file
        - parallel: override self.parallel
        - np: override self.np (only if parallel=True)
        """
        img = params.get("image")
        if img is not None:
            import image3kit as ik

            cur = Path.cwd()
            try:
                os.chdir(case.case_dir)
                img_copy = ik.VxlImgU8(img)
                # Ensure voxel coordinates for meshing/smoothing
                img_copy.spacing = ik.dbl3(1, 1, 1)
                img_copy.to_foam()
            finally:
                os.chdir(cur)
            return MeshBuildResult(case_dir=case.case_dir)

        mhd_file = params.get("mhd_file", "input.mhd")
        parallel = params.get("parallel", self.parallel)
        np = params.get("np", self.np)

        if parallel:
            return _voxel_to_foam_par(case, mhd_file, np)
        return _voxel_to_foam(case, mhd_file)


def _stl_to_cartesian2d_mesh(
    case: FoamCase,
    stl_file: str,
    max_first_layer_thickness: float | None = None,
    rel_thickness_tol: float | None = None,
) -> MeshBuildResult:
    """Generate a 2D mesh from an STL using cartesian2DMesh.

    Composes CfMeshBackend(dimension=2); kept as a function for the existing
    call site in StlGeometry.

    Used by StlGeometry variant.
    """
    if max_first_layer_thickness is not None:
        # Additional parameters would be set in meshDict
        pass
    return CfMeshBackend(dimension=2).mesh_surface(case, case.case_dir / stl_file, {})


def _cfmesh_roundtrip(
    case: FoamCase,
    voxel_image: str,
    surface_tool: str = "vxlToSurf",
) -> MeshBuildResult:
    """Voxel → STL → cfMesh → ofMesh2Voxel roundtrip.

    Used by CFMeshGeometry variant (AllRunImageTwoPhaseCFMesh).

    Args:
        case: FoamCase directory.
        voxel_image: Input voxel image file.
        surface_tool: Tool to extract STL surface from voxel image.

    Returns:
        MeshBuildResult.
    """
    # Extract surface.
    case.run_app(surface_tool, [voxel_image])

    # Build mesh via cfMesh (simplified; real implementation needs meshDict setup).
    case.run_app("cartesianMesh")
    case.run_app("checkMesh")

    # Convert back to voxel.
    case.run_app("ofMesh2Voxel")

    return MeshBuildResult(case_dir=case.case_dir)


def _read_mesh_stats(case_dir: Path | str) -> tuple[int, int, int]:
    """Read nPoints, nFaces, nCells from polyMesh.

    Returns:
        (n_points, n_faces, n_cells)
    """
    case_dir = Path(case_dir)
    poly_mesh = case_dir / "constant" / "polyMesh"

    n_points = 0
    points_file = poly_mesh / "points"
    if points_file.exists():
        # Count lines with coordinates.
        n_points = len([l for l in points_file.read_text().strip().split("\n") if "(" in l])

    n_faces = 0
    faces_file = poly_mesh / "faces"
    if faces_file.exists():
        # Count face entries (lines starting with a number).
        text = faces_file.read_text()
        n_faces = text.count("(")

    n_cells = 0
    cells_file = poly_mesh / "cells"
    if cells_file.exists():
        text = cells_file.read_text()
        n_cells = text.count("(")

    return n_points, n_faces, n_cells
