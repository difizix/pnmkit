"""Two-phase (porefoam2f) case runner (Phase 2).

TwoPhaseCaseRunner extends CaseTemplateRunner with porefoam2f-specific logic:
- Single-phase flag branch (oilFilldFrac > 1 → _SP suffix)
- QOil/QWat flow rate computation from bounding box
- Inlet/outlet BC setup (flowRate, meanValue, contact angle)
- Initial saturation (voxelAlphaFieldToFoam or setFields box-fill)
- Directory naming matching bash exactly for downstream tooling
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .. import runtime as rt
from ..foam.foam_case import CaseTemplateRunner, FoamCase, darcy_flow_rate_from_bbox, read_points_bbox
from ..foam.foam_dict import FileKV
from ..foam.foam_image import rewrite_mhd_header
from ..foam.foam_mesh import GeometryBuilder


class TwoPhaseCaseRunner(CaseTemplateRunner):
    """Runner for porefoam2f two-phase cases (interFaceFoam).

    Adds porefoam2f-specific logic on top of the generic CaseTemplateRunner:
    - Single-phase mode when oilFilldFrac > 1
    - Darcy velocity → flowRate conversion at inlet
    - Contact angle BCs (theta0/thetaA/thetaR)
    - Initial saturation setup
    - Directory naming matching bash's exact format
    """

    def __init__(
        self,
        template_dir: str | Path,
        geometry_builder: GeometryBuilder,
        work_dir: str | Path | None = None,
        extra_template_dir: str | Path | None = None,
        inlet: str = "Left",
        outlet: str = "Right",
        vxl_size: float = 5e-6,
    ) -> None:
        super().__init__(template_dir, geometry_builder, work_dir if work_dir is not None else Path.cwd())
        self.extra_template_dir = Path(extra_template_dir) if extra_template_dir else None
        self.inlet = inlet
        self.outlet = outlet
        self.vxl_size = vxl_size

    # ---- directory naming ----

    def mesh_dir_name(self, data_file: str, params: dict[str, Any], mesh_tag: str = "") -> str:
        """Compute mesh directory name matching bash format.

        bash format: ${dataFile}_${RefineLevel}_C${cementPCent}_R${RSphere}_Y${ScaleY}_Z${ScaleZ}
        (from AllRunImageTwoPhase_spack:150)
        Or for voxel cases: ${dataFile}${meshTag}
        """
        if "cementPCent" in params or "RSphere" in params:
            rl = params.get("RefineLevel", 12)
            cp = params.get("cementPCent", 20)
            rs = params.get("RSphere", 20)
            sy = params.get("ScaleY", 1)
            sz = params.get("ScaleZ", 1)
            return f"{data_file}{mesh_tag}_{rl}_C{cp}_R{rs}_Y{sy}_Z{sz}"
        return f"{data_file}{mesh_tag}"

    def run_dir_name(
        self,
        mesh_dir_name: str,
        params: dict[str, Any],
        case_tag: str = "",
    ) -> str:
        """Compute run directory name matching bash format.

        bash format: ${mshDir}${caseTag}_Uo${UD1}w${UD0}CAw${theta0}
        (from AllRunImageTwoPhase_spack:283)

        If oilFilldFrac > 1: ${mshDir}_SP (single-phase)
        (from AllRunImageTwoPhase_spack:288)
        """
        oil_frac = params.get("oilFilldFrac", 0.1)
        if oil_frac > 1.0:
            return f"{mesh_dir_name}_SP"

        ud1 = params.get("UD1", 200)
        ud0 = params.get("UD0", 10)
        theta0 = params.get("theta0", 150)
        return f"{mesh_dir_name}{case_tag}_Uo{ud1}w{ud0}CAw{theta0}"

    # ---- mesh setup ----

    def setup_mesh(
        self,
        data_file: str,
        geometry_params: dict[str, Any],
        mesh_tag: str = "",
        numerics_edits: Sequence[FileKV] | None = None,
    ) -> FoamCase:
        """Create and mesh a case directory.

        Args:
            data_file: Base name (e.g. 'spack').
            geometry_params: Passed to GeometryBuilder.build().
            mesh_tag: Optional suffix for mesh dir name.
            numerics_edits: Post-meshing dict edits.

        Returns:
            FoamCase for the meshed directory.
        """
        target = self.mesh_dir_name(data_file, geometry_params, mesh_tag)
        mesh_path = self.work_dir / target
        if (mesh_path / "constant" / "polyMesh" / "points").exists():
            rt.disp(f"Mesh already exists: {target}, skipping creation")
            return FoamCase(mesh_path)

        if mesh_path.exists():
            msg = f"Mesh folder {mesh_path} exists but mesh is not there. Remove it and rerun to regenerate."
            raise RuntimeError(msg)

        # Copy template.
        mesh_path = self._copy_template(target)
        case = FoamCase(mesh_path)

        # Copy postProcessDict if available.
        pp_src = self.work_dir / f"postProcessDict_{data_file}"
        if pp_src.exists():
            rt.run_sh(str(mesh_path), f"cp {pp_src} system/postProcessDict")

        # Build mesh via GeometryBuilder.
        rt.disp(f"########### Creating mesh: {target} ##########")
        self.geometry_builder.build(case, geometry_params)

        # Apply smoothing passes if configured
        n_iter = geometry_params.get("smoothMeshNIter", 0)
        relax = geometry_params.get("smoothMeshRelax", 0.1)
        bnd = geometry_params.get("smoothMeshBoundary", True)
        intnl = geometry_params.get("smoothMeshInternal", True)
        bnd_layers = geometry_params.get("smoothMeshBoundaryLayers", 0)
        vol_iso = geometry_params.get("smoothMeshVolIso", 1)
        for ii in range(1, n_iter + 1):
            if bnd:
                case.run_app(
                    "smoothFMesh",
                    [str(relax), "10", str(bnd_layers), str(vol_iso)],
                    log_name=f"log.smoothFMesh-{ii}.0",
                    skip_if_exists=False,
                )
            if intnl:
                case.run_app(
                    "smoothFMesh",
                    [str(relax), "10", "4", str(vol_iso)],
                    log_name=f"log.smoothFMesh-{ii}.1",
                    skip_if_exists=False,
                )

        # Set boundary type on Grainwalls.
        case.edit([FileKV("constant/polyMesh/boundary", "Grainwalls.type", "wall")])

        # Transform points to physical scale if still in voxel coordinates (>0.01)
        bbox = read_points_bbox(case.case_dir)
        if max(abs(bbox[3]), abs(bbox[4]), abs(bbox[5])) > 0.01 and self.vxl_size > 0:
            case.transform_points((self.vxl_size, self.vxl_size, self.vxl_size))

        # Run mesh utilities.
        case.renumber_mesh(skip_if_exists=False)
        case.check_mesh(skip_if_exists=False)
        self._run_remove_extras(case)

        # Apply numerics edits.
        if numerics_edits:
            case.edit(numerics_edits)

        return case

    # ---- run case setup ----

    def setup_run_case(
        self,
        mesh_case: FoamCase,
        params: dict[str, Any],
        case_tag: str = "",
    ) -> FoamCase:
        """Set up a run (simulation) case from an existing mesh case.

        Copies mesh case → run dir, applies BC/IC edits, decomposes.

        Args:
            mesh_case: FoamCase with completed mesh.
            params: Simulation parameters (UD1, UD0, theta0, oilFilldFrac, etc.).
            case_tag: Optional tag for run dir name.

        Returns:
            FoamCase for the set-up run directory.
        """
        msh_name = mesh_case.case_dir.name
        run_name = self.run_dir_name(msh_name, params, case_tag)
        run_path = self.work_dir / run_name
        run_case = FoamCase(run_path)

        # If run dir already set up (has polyMesh/points), return it.
        if run_path.exists() and (run_path / "constant" / "polyMesh" / "points").exists():
            rt.disp(f"Run case already exists: {run_name}")
            return run_case

        # Single-phase flag.
        oil_frac = params.get("oilFilldFrac", 0.1)
        is_single_phase = oil_frac > 1.0

        if is_single_phase:
            rt.disp(f"oilFilldFrac {oil_frac} > 1 → single-phase mode")
            end_time = 0.005
            max_s1 = 1.999
            min_s1 = -0.001
        else:
            end_time = params.get("endTime", 0.2)
            max_s1 = 0.999
            min_s1 = 0.001

        rt.disp(f"########### Preparing parallel case: {run_name} ##########")

        # Copy mesh case → run dir.
        rt.run_sh(str(self.work_dir), f"mkdir -p {run_path}")
        rt.run_sh(str(run_path), f"cp -r {mesh_case.case_dir}/0 .")
        rt.run_sh(str(run_path), f"cp -r {mesh_case.case_dir}/constant .")
        rt.run_sh(str(run_path), f"cp -r {mesh_case.case_dir}/system .")
        log_check = mesh_case.case_dir / "log.checkMesh"
        if log_check.exists():
            shutil.copy(log_check, run_path / "log.checkMesh")
        rt.run_sh(str(run_path), f"touch {run_path}.foam")

        # ControlDict edits.
        case_edit: list[FileKV] = [
            FileKV("system/controlDict", "maxS1", str(max_s1)),
            FileKV("system/controlDict", "minS1", str(min_s1)),
            FileKV("system/controlDict", "writeFormat", "ascii"),
            FileKV("system/controlDict", "endTime", str(end_time)),
        ]
        for key in ("maxDeltaT", "maxAlphaCo"):
            if key in params:
                case_edit.append(FileKV("system/controlDict", key, str(params[key])))

        run_case.edit(case_edit)

        # FvSolution edits (surface tension / discretization params).
        fv_sol: list[FileKV] = []
        for key in (
            "cAlpha",
            "pcThicknessFactor",
            "surfaceForceModel",
            "fcCorrectTangent",
            "smoothingKernel",
            "smoothingRelaxFactor",
            "wallSmoothingKernel",
            "fcdFilter",
        ):
            if key in params:
                fv_sol.append(FileKV("system/fvSolution", key, str(params[key])))
        if fv_sol:
            run_case.edit(fv_sol)

        # Compute flow rates from bbox.
        bbox = read_points_bbox(run_case.case_dir)
        rt.disp(f"Bounding box: {bbox}")

        ud1 = params.get("UD1", 200)
        ud0 = params.get("UD0", 10)
        q_oil = darcy_flow_rate_from_bbox(bbox, ud1)
        q_wat = darcy_flow_rate_from_bbox(bbox, ud0)
        rt.disp(f"QOil: {q_oil}, QWat: {q_wat}")

        # Boundary conditions.
        theta0 = params.get("theta0", 150)
        theta_in = params.get("thetaIn", 90)
        theta_out = params.get("thetaOut", 90)
        theta_a = params.get("thetaA", theta0)
        theta_r = params.get("thetaR", theta0)
        pd_mean1 = params.get("pdMeanValue1", 0)
        pd_mean2 = params.get("pdMeanValue2", 0)

        bc_edits = [
            # Inlet flow rates (U).
            FileKV("0/U", f"{self.inlet}.flowRate1", f"{q_oil}"),
            FileKV("0/U", f"{self.inlet}.flowRate0", f"{q_wat}"),
            # Outlet mean pressures (pd).
            FileKV("0/pd", f"{self.outlet}.meanValue1", f"{pd_mean1}"),
            FileKV("0/pd", f"{self.outlet}.meanValue2", f"{pd_mean2}"),
            # Grainwalls contact angle.
            FileKV("0/alpha1", "Grainwalls.theta0", f"{theta0}", optional=True),
            FileKV("0/alpha1", "Grainwalls.thetaR", f"{theta_r}", optional=True),
            FileKV("0/alpha1", "Grainwalls.thetaA", f"{theta_a}", optional=True),
            FileKV("constant/transportProperties", "theta", f"theta [ 0 0 0 0 0 0 0 ] {theta0}"),
            # Inlet/outlet contact angles.
            FileKV("0/alpha1", f"{self.inlet}.theta0", f"{theta_in}", optional=True),
            FileKV("0/alpha1", f"{self.outlet}.theta0", f"{theta_out}", optional=True),
        ]
        run_case.edit(bc_edits)

        # Initial saturation.
        self._set_initial_saturation(run_case, bbox, params)

        # Decomposition.
        n_proc = params.get("nProc", 24)

        # Use processor-specific decomposeParDict if available.
        if self.extra_template_dir:
            custom_dp = self.extra_template_dir / "system" / f"decomposeParDict.{n_proc}"
            if custom_dp.exists():
                shutil.copy(custom_dp, run_case.case_dir / "system" / "decomposeParDict")
            else:
                rt.disp(f"File {custom_dp} not found, using single-level scotch")

        run_case.edit(
            [
                FileKV("system/decomposeParDict", "numberOfSubdomains", str(n_proc)),
                FileKV("system/decomposeParDict", "method", "scotch"),
            ]
        )

        run_case.decompose_par(n_proc, skip_if_exists=False)
        run_case.renumber_mesh(parallel=True, np=n_proc, skip_if_exists=False)

        # Fix pressure BC in processor dirs (add 'adjoint no;' to fixedFluxPressure).
        self._fix_processor_pressure_bc(run_case)

        # Switch to binary output.
        run_case.edit([FileKV("system/controlDict", "writeFormat", "binary")])

        return run_case

    # ---- run solver ----

    def run_simulation(
        self,
        run_case: FoamCase,
        params: dict[str, Any],
        solver: str = "interFaceFoam",
    ) -> None:
        """Run the simulation solver on the set-up case.

        Args:
            run_case: FoamCase for the run directory.
            params: Parameters (nProc for MPI).
            solver: Solver name (default: interFaceFoam).
        """
        log_file = run_case.case_dir / f"log.{solver}"
        if log_file.exists():
            tail = log_file.read_text(errors="ignore")[-200:]
            if "\nEnd\n" in tail or tail.strip().endswith("End"):
                rt.disp(f"Simulation {solver} already completed on {run_case.case_dir.name}")
                return

        n_proc = params.get("nProc", 24)
        rt.disp(f"########### Running simulation on {run_case.case_dir.name} ##########")
        run_case.run_solver(solver, parallel=True, np=n_proc)

    # ---- private helpers ----

    def _set_initial_saturation(
        self,
        case: FoamCase,
        bbox: tuple[float, float, float, float, float, float],
        params: dict[str, Any],
    ) -> None:
        """Set initial alpha1 field.

        - oilFilldFrac < 0: use voxel image (voxelAlphaFieldToFoam).
        - oilFilldFrac >= 0: use setFields to fill a box near inlet.
        """
        oil_frac = params.get("oilFilldFrac", 0.1)
        vmin, _, _, xmax, _, _ = bbox

        if oil_frac < 0.0:
            # Voxel-image initialization.
            vse = params.get("VSElml", 1)
            n_grow = params.get("nGrowAlpha", 0)
            self._init_saturation_from_voxel(case, vse, n_grow, params)
        else:
            # Box-fill initialization (setFields).
            x_init = vmin + (xmax - vmin) * oil_frac
            rt.disp(f"xInitAlpha: {x_init}")
            # OpenFOAM dict format for the box.
            box_val = f"(-1. -1. -1.) ({x_init} 1000 1000);"
            case.edit([FileKV("system/setFieldsDict", "box", box_val)])
            case.run_app("setFields", skip_if_exists=False)

    def _init_saturation_from_voxel(
        self,
        case: FoamCase,
        vse: Any,
        n_grow: int,
        _params: dict[str, Any],
    ) -> None:
        """Initialize alpha1 from voxel image."""
        if isinstance(vse, str) and vse == "alpha1.mhd":
            # Direct alpha1 field provided.
            rt.run_sh(str(case.case_dir), "cp -r ../alpha1.* . 2>/dev/null || true")
            n_grow_arg = str(n_grow) if n_grow else "0"
            case.run_app("voxelAlphaFieldToFoam", ["alpha1.mhd", "-nGrowAlpha", n_grow_arg], skip_if_exists=False)
        else:
            # Requires skelor outputs (SNet_corners.mhd → threshold → alpha1.mhd).
            rt.disp(f"VSElml={vse} != 'alpha1.mhd' requires skelor outputs")
            mesh_name = case.case_dir.name
            snet = mesh_name
            rt.run_sh(
                str(case.case_dir),
                f"cp -r ../{snet}.* . 2>/dev/null || true",
            )
            # Replace Unit in corners.mhd and add threshold.
            corners_file = case.case_dir / f"{snet}_corners.mhd"
            if corners_file.exists():
                rewrite_mhd_header(corners_file, unit=self.vxl_size, append_text="\nthreshold 120 2000\n")
            case.run_app("voxelImageProcPy", [f"{snet}_corners.mhd", "-o", "alpha1.mhd", "UChar"], skip_if_exists=False)
            n_grow_arg = str(n_grow) if n_grow else "0"
            case.run_app("voxelAlphaFieldToFoam", ["alpha1.mhd", "-nGrowAlpha", n_grow_arg], skip_if_exists=False)

    def _fix_processor_pressure_bc(self, case: FoamCase) -> None:
        """Add 'adjoint no;' to fixedFluxPressure patches in processor/*/0/pd."""
        pd_files = sorted(case.case_dir.glob("processor*/0/pd"))
        for pd_file in pd_files:
            text = pd_file.read_text()
            # Add adjoint no; after fixedFluxPressure; (if not already present).
            text = re.sub(
                r"(fixedFluxPressure;)(?!.*adjoint)",
                r"\1\n        adjoint no;",
                text,
            )
            pd_file.write_text(text)

    @staticmethod
    def _run_remove_extras(case: FoamCase) -> None:
        """Clean up extra mesh files (from bash RunRemoveExtras)."""
        rt.run_sh(
            str(case.case_dir),
            (
                "rm -f 0/ccx 0/ccy 0/ccz "
                "0/cell* 0/point* 0/*Level "
                "constant/polyMesh/*Level "
                "constant/polyMesh/*Zones "
                "constant/polyMesh/*History "
                "constant/polyMesh/*Index "
                "log.faceSet.*"
            ),
        )
