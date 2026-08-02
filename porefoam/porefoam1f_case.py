"""Single-phase (porefoam1f) case runner (Phase 5, item 6).

SinglePhaseCaseRunner extends CaseTemplateRunner for porefoam1f single-phase
simulations: pressure-drop BCs, iPotentialFoam→icoNSFoam sequence, no alpha/CA.
Used by the four porefoam1f variants (serial, parallel, distributed, ParSaveMemory).

Key differences from TwoPhaseCaseRunner:
- No alpha1 field or contact angle BCs
- Pressure-drop boundary condition set on direction-specific patches (X/Y/Z)
- Solver sequence: (optional) iPotentialFoam → icoNSFoam → calc_distributions
- FOAM2Voxel post-processing step
- Uses VoxelImageGeometry for voxel→FOAM meshing (voxelToFoam / voxelToFoamPar)
"""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .. import runtime as rt
from ..foam.foam_case import CaseTemplateRunner, FoamCase
from ..foam.foam_dict import FileKV, apply_edits
from ..foam.foam_image import find_image_file, rewrite_mhd_header
from ..foam.foam_mesh import GeometryBuilder


class SinglePhaseCaseRunner(CaseTemplateRunner):
    """Runner for porefoam1f single-phase cases.

    Handles:
    - Direction-specific field renaming (p.X→p, U.X→U)
    - Pressure-drop BC setup via setBoundaryCondition
    - iPotentialFoam → icoNSFoam → calc_distributions solver sequence
    - FOAM2Voxel / FOAM2VoxelSaveMemory post-processing
    - Serial, MPI, and distributed run modes
    """

    def __init__(
        self,
        template_dir: str | Path,
        geometry_builder: GeometryBuilder,
        work_dir: str | Path = Path.cwd(),
        extra_template_dir: str | Path | None = None,
        inlet: str = "Left",
        outlet: str = "Right",
    ) -> None:
        super().__init__(template_dir, geometry_builder, work_dir)
        self.extra_template_dir = Path(extra_template_dir) if extra_template_dir else None
        self.inlet = inlet
        self.outlet = outlet

    # ---- directory naming ----

    def case_name(
        self,
        data_file: str,
        params: dict[str, Any],
        prefix: str | None = None,
    ) -> str:
        """Compute case directory name matching bash format.

        bash format (from AllRunImage):
            $prefix$dataFile$tag-$p-$direction

        Args:
            data_file: Base name without extension.
            params: Contains 'pressure', 'direction', 'tag', 'case_tag'.
            prefix: Optional subdirectory prefix.

        Returns:
            Case directory name.
        """
        tag = params.get("tag", "")
        pressure = params.get("pressure", 1)
        direction = params.get("direction", "X")
        case_tag = params.get("case_tag", "")

        name = f"{data_file}{tag}{case_tag}-{pressure}-{direction}"
        if prefix:
            name = f"{prefix}/{name}"
        return name

    # ---- image file handling ----

    @staticmethod
    def find_image_file(data_file: str, work_dir: Path) -> Path | None:
        """Find the image file for a given data_file stem.

        Checks extensions in order: .mhd, .nhdr, .tif, .am, .gz
        """
        return find_image_file(data_file, work_dir)

    @staticmethod
    def prepare_mhd_file(
        case: FoamCase,
        data_file: str,
        image_path: Path,
        voxel_commands: str | None = None,
    ) -> Path:
        """Prepare the input .mhd file in the case directory.

        Handles:
        - Copying .mhd and fixing ElementDataFile path
        - Converting .nhdr → .mhd
        - Handling .tif/.am → .mhd stub
        - Appending optional voxelCommands

        Returns:
            Path to the prepared .mhd file inside the case.
        """
        mhd_name = f"{data_file}_input.mhd"
        mhd_path = case.case_dir / mhd_name

        ext = image_path.suffix
        if ext == ".gz":
            ext = image_path.stem.rsplit(".", 1)[-1] + ".gz"

        if ext in (".mhd", ".mhd.gz"):
            # Copy and fix ElementDataFile.
            rt.run_sh(str(case.case_dir), f"cp {image_path} {mhd_path}")
            rewrite_mhd_header(mhd_path, element_data_file=f"../../{image_path.name}")
        elif ext in (".nhdr", ".nhdr.gz"):
            # Parse .nhdr and create .mhd.
            nhdr = image_path.read_text()
            # Extract sizes.
            sizes_line = re.search(r"sizes\s*:\s*([^\\n]+)", nhdr)
            if not sizes_line:
                msg = f"No sizes in {image_path}"
                raise ValueError(msg)
            dims = sizes_line.group(1).strip()

            # Extract directions/elementSize.
            dir_line = re.search(r"directions\s*:\s*([^\\n]+)", nhdr)
            elem_size = ""
            if dir_line:
                raw = dir_line.group(1)
                elem_size = re.sub(r"[()\s,:]", " ", raw).strip()

            mhd_content = f"""ObjectType =  Image
NDims =       3
ElementType = MET_UCHAR

DimSize =  {dims}

ElementSize =  {elem_size}
Offset = 0 0 0

ElementDataFile = ../../{image_path.name}

"""
            mhd_path.write_text(mhd_content)
        elif ext in (".tif", ".am"):
            # Stub .mhd — user must verify.
            mhd_path.write_text(f"""ObjectType =  Image
NDims =       3
ElementType = MET_UCHAR

ElementDataFile = ../../{image_path.name}

""")
            rt.disp(f"Generated stub {mhd_path}. Please verify contents and provide a correct .mhd if needed.")
        else:
            msg = f"Unsupported image extension: {ext}"
            raise ValueError(msg)

        if voxel_commands:
            mhd_path.write_text(mhd_path.read_text() + f"\n{voxel_commands}\n")

        return mhd_path

    # ---- boundary condition setup ----

    def setup_directional_fields(
        self,
        case: FoamCase,
        direction: str,
    ) -> None:
        """Rename direction-specific field files and remove extras.

        bash equivalent:
            cd $caseName/0 && mv p.$direction p; rm p.*
            cd $caseName/0 && mv U.$direction U; rm U.*
        """
        zero_dir = case.case_dir / "0"
        if not zero_dir.exists():
            return

        # Pressure field.
        p_dir = zero_dir / f"p.{direction}"
        if p_dir.exists():
            rt.run_sh(str(zero_dir), f"mv p.{direction} p")
        # Remove other p.* files.
        for f in zero_dir.glob("p.*"):
            f.unlink(missing_ok=True)

        # Velocity field.
        u_dir = zero_dir / f"U.{direction}"
        if u_dir.exists():
            rt.run_sh(str(zero_dir), f"mv U.{direction} U")
        for f in zero_dir.glob("U.*"):
            f.unlink(missing_ok=True)

    @staticmethod
    def set_boundary_condition(
        case: FoamCase,
        direction: str,
        value: str,
        patches: list[str] | None = None,
        field: str = "p",
    ) -> None:
        """Set a boundary condition value on direction-specific patches.

        Reproduces setBoundaryCondition from foam.bashrc. Finds patches whose
        name contains the direction keyword and sets the 'value' entry,
        inserting it if the patch's template BC doesn't have one yet (e.g. a
        non-fixedValue type) — via foam.foam_dict's brace-depth-aware editor,
        which also correctly handles patch blocks containing nested braces
        (the old regex-based version here did not).
        """
        zero_dir = case.case_dir / "0"
        field_file = zero_dir / field
        if not field_file.exists():
            rt.disp(f"Field file {field_file} not found, skipping BC setup.")
            return

        # Default patches by direction (matching bash pattern).
        if patches is None:
            direction_map = {
                "X": ["Right"],
                "Y": ["Top"],
                "Z": ["Front"],
            }
            patches = direction_map.get(direction, ["Right"])

        clean_value = re.sub(r"^value\b\s*", "", value.strip().rstrip(";"))

        apply_edits(
            case.case_dir,
            [
                FileKV(f"0/{field}", f"{patch}.value", clean_value, insert_if_missing=True)
                for patch in patches
            ],
        )

    def set_pressure_bc(
        self,
        case: FoamCase,
        direction: str,
        pressure: float,
    ) -> None:
        """Set uniform pressure BC on the inlet patch for the given direction.

        Inlet patches: X -> Left, Y -> Bottom, Z -> Back.
        """
        inlet_map = {
            "X": ["Left"],
            "Y": ["Bottom"],
            "Z": ["Back"],
        }
        patches = inlet_map.get(direction, ["Left"])
        self.set_boundary_condition(
            case,
            direction,
            f"uniform {pressure}",
            patches=patches,
            field="p",
        )

    # ---- solver execution ----

    def run_potential_flow(
        self,
        case: FoamCase,
        params: dict[str, Any],
        skip: bool = False,
    ) -> None:
        """Run iPotentialFoam for initial velocity field.

        Can be skipped via params['skip_potential'] or the 'skip' flag.
        """
        if skip or params.get("skip_potential", False):
            rt.disp("Skipping iPotentialFoam.")
            return

        n_proc = params.get("nProc", 1)
        mode = params.get("mode", "serial")
        case.run_mode("iPotentialFoam", mode, n_proc, hostfile=params.get("hostfile"))

    def run_navier_stokes(
        self,
        case: FoamCase,
        params: dict[str, Any],
        solver: str = "icoNSFoam",
        skip: bool = False,
    ) -> None:
        """Run the Navier-Stokes solver (icoNSFoam or icoNSFoamNSD).

        Reproduces:
            runMPI/runDistributed icoNSFoam $nProc
            mv log.icoNSFoam log.icoNSFoam.1
        """
        if skip or params.get("skip_flow", False):
            rt.disp("Skipping Navier-Stokes solver.")
            return

        n_proc = params.get("nProc", 1)
        mode = params.get("mode", "serial")
        case.run_mode(solver, mode, n_proc, hostfile=params.get("hostfile"))

        # Rename log to preserve it (matching bash mv log.icoNSFoam log.icoNSFoam.1).
        log_path = case.case_dir / f"log.{solver}"
        if log_path.exists():
            log_path.rename(case.case_dir / f"log.{solver}.1")

    def run_calc_distributions(
        self,
        case: FoamCase,
        params: dict[str, Any],
        skip: bool = False,
    ) -> None:
        """Run calc_distributions utility.

        Reproduces runMPI/runDistributed calc_distributions $nProc.
        """
        if skip:
            return

        n_proc = params.get("nProc", 1)
        mode = params.get("mode", "serial")
        case.run_mode("calc_distributions", mode, n_proc, hostfile=params.get("hostfile"))

    def run_foam2voxel(
        self,
        case: FoamCase,
        params: dict[str, Any],
        output_format: str = "raw.gz",
        save_memory: bool = False,
        skip: bool = False,
    ) -> None:
        """Run FOAM2Voxel or FOAM2VoxelSaveMemory post-processing.

        Reproduces:
            runApp FOAM2Voxel vxlImage.mhd "$nProc" "$outPutFormat" [t]
            runApp FOAM2VoxelSaveMemory vxlImage.mhd "$nProc" "$outPutFormat"
        """
        if skip:
            return

        n_proc = params.get("nProc", 1)
        tool = "FOAM2VoxelSaveMemory" if save_memory else "FOAM2Voxel"

        # FOAM2VoxelSaveMemory doesn't use the 't' flag.
        if save_memory:
            args = ["vxlImage.mhd", str(n_proc), output_format]
        else:
            # Include 't' flag for threaded operation in parallel cases.
            args = ["vxlImage.mhd", str(n_proc), output_format, "t"]

        case.run_app(tool, args)

    # ---- setup mesh case ----

    def setup_mesh(
        self,
        data_file: str,
        geometry_params: dict[str, Any],
        case_params: dict[str, Any],
        numerics_edits: Sequence[FileKV] | None = None,
        voxel_commands: str | None = None,
    ) -> FoamCase:
        """Set up a single-phase case directory with voxel mesh.

        This is a convenience method that:
        1. Copies template
        2. Prepares .mhd file
        3. Builds mesh via GeometryBuilder
        4. Renames direction-specific fields
        5. Applies numerics edits
        """
        case_name = self.case_name(data_file, case_params)
        case_path = self.work_dir / case_name

        # Skip if exists.
        if case_path.exists():
            rt.disp(f"Case already exists: {case_name}")
            return FoamCase(case_path)

        # Copy template, build mesh via GeometryBuilder, apply numerics edits.
        case = self.setup_mesh_case(case_name, geometry_params, numerics_edits)

        # Rename direction-specific fields (independent of mesh building, so
        # safe to do after — matches CaseTemplateRunner.setup_mesh_case()'s
        # copy → build → edit order).
        direction = case_params.get("direction", "X")
        self.setup_directional_fields(case, direction)

        # Create .foam file.
        foam_name = case_name.replace("/", "-")
        rt.run_sh(str(case.case_dir), f"touch {foam_name}.foam")

        return case

    # ---- setup run case ----

    def setup_run(
        self,
        case: FoamCase,
        params: dict[str, Any],
        pressure: float,
        direction: str,
    ) -> None:
        """Apply run-specific settings (BCs, controlDict, decomposition).

        Called after setup_mesh() before running solvers.
        """
        n_proc = params.get("nProc", 1)
        mode = params.get("mode", "serial")

        # Set pressure BC.
        self.set_pressure_bc(case, direction, pressure)

        # ControlDict settings.
        edits = [
            FileKV("system/controlDict", "endTime", str(params.get("endTime", 0.1))),
            FileKV("system/controlDict", "writeInterval", "1000"),
        ]
        case.edit(edits)

        # fvSolution: relaxation for U.
        case.edit([FileKV("system/fvSolution", "relaxationFactors.U", "0.5")])

        # For parallel/distributed modes, decompose.
        if mode in ("parallel", "distributed"):
            n_proc_x = params.get("nProcX", 2)
            n_proc_y = params.get("nProcY", 2)
            n_proc_z = params.get("nProcZ", 2)

            # Copy 0 to all processor dirs (after voxelToFoamPar creates them).
            proc_dirs = sorted(case.case_dir.glob("processor*"))
            if proc_dirs:
                for proc_dir in proc_dirs:
                    rt.run_sh(str(case.case_dir), f"cp -r 0 {proc_dir}")

                # Update decomposeParDict.
                case.edit(
                    [
                        FileKV("system/decomposeParDict", "numberOfSubdomains", str(n_proc)),
                        FileKV("system/decomposeParDict", "hierarchicalCoeffs.n", f"( {n_proc_x} {n_proc_y} {n_proc_z} )"),
                        FileKV("system/decomposeParDict", "simpleCoeffs.n", f"( {n_proc_x} {n_proc_y} {n_proc_z} )"),
                    ]
                )

                # Set BCs in all processor dirs.
                for proc_dir in proc_dirs:
                    self.set_pressure_bc(
                        FoamCase(proc_dir),
                        direction,
                        pressure,
                    )

                # Renumber. mode is "parallel" or "distributed" here (see the
                # enclosing `if mode in ("parallel", "distributed")` above),
                # so run_mode's serial branch is unreachable.
                case.run_mode("renumberMesh", mode, n_proc, ["-overwrite"], hostfile=params.get("hostfile"))

    # ---- full run pipeline ----

    def run_case(
        self,
        case: FoamCase,
        params: dict[str, Any],
        pressure: float,
        direction: str,
        output_format: str = "raw.gz",
        save_memory: bool = False,
        solver: str = "icoNSFoam",
    ) -> None:
        """Run the complete single-phase simulation pipeline.

        Steps:
        1. Apply run setup (BCs, decomposition)
        2. (optional) iPotentialFoam
        3. icoNSFoam (or icoNSFoamNSD)
        4. calc_distributions
        5. FOAM2Voxel / FOAM2VoxelSaveMemory
        """
        rt.disp(f"########### Running simulation: {case.case_dir.name} ##########")

        self.setup_run(case, params, pressure, direction)

        self.run_potential_flow(case, params)
        self.run_navier_stokes(case, params, solver=solver)
        self.run_calc_distributions(case, params)
        self.run_foam2voxel(case, params, output_format=output_format, save_memory=save_memory)

        rt.disp("..................            END              .......................")
