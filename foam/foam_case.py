"""OpenFOAM case management primitives (Phase 1 — Generic core).

Provides:
- FoamCase: wrapper around run_app/run_mpi/run_distributed/decompose_par/renumber_mesh patterns
  from foam.bashrc, all via run_sh with skip_if_exists idempotency.
- read_points_bbox(): direct polyMesh/points parsing (no log-scraping).
- CaseTemplateRunner: base class that templates a case, invokes a GeometryBuilder,
  applies numerics edits, reads bbox — no solver-specific logic.
"""

import os
import re
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import runtime as rt
from .foam_dict import FileKV, apply_edits


def ensure_foam_env() -> None:
    """Ensure OpenFOAM environment variables (WM_*, FOAM_*, PATH, LD_LIBRARY_PATH) are set."""
    if "WM_PROJECT" in os.environ and "FOAM_LIBBIN" in os.environ:
        return
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "src" / "script" / "foam.bashrc",
    ]
    if "msSrc" in os.environ:
        candidates.append(Path(os.environ["msSrc"]) / "script" / "foam.bashrc")
    for foam_bashrc in candidates:
        if foam_bashrc.exists():
            res = subprocess.run(
                ["bash", "-c", f"source {foam_bashrc} >/dev/null 2>&1 && env -0"],
                capture_output=True,
            )
            if res.returncode == 0:
                for item in res.stdout.decode("utf-8", errors="ignore").split("\0"):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        if (
                            k in ("PATH", "LD_LIBRARY_PATH", "MPI_BUFFER_SIZE", "WM_PROJECT", "WM_PROJECT_DIR")
                            or k.startswith(("WM_", "FOAM_"))
                        ):
                            os.environ[k] = v
                            rt.msEnv[k] = v
                break


ensure_foam_env()


class FoamCase:
    """Thin wrapper around OpenFOAM utility execution in a case directory.

    All run_* methods use run_sh() with skip_if_exists=True by default,
    reproducing bash foam.bashrc's "remove log to rerun" idempotency.
    """

    def __init__(self, case_dir: Path | str) -> None:
        self.case_dir = Path(case_dir)
        ensure_foam_env()

    def _log_path(self, app_name: str) -> Path:
        return self.case_dir / f"log.{app_name}"

    # ---- single-process app ----

    def run_app(
        self,
        app: str,
        args: Sequence[str] | None = None,
        log_name: str | None = None,
        skip_if_exists: bool = True,
    ) -> None:
        """Run a single-process OpenFOAM utility.

        Reproduces bash `runApp`: logs to `log.<app>`, skips if log exists
        (remove log to force re-run).
        """
        args = args or []
        script = app + " " + " ".join(args)
        if log_name is None:
            log_name = f"log.{app}"
        log_path = self.case_dir / log_name
        if skip_if_exists and log_path.exists():
            rt.disp(f"Skipping '{script}': log exists ({log_path})")
            return
        rt.disp(f"Running '{script}' > {log_name}")
        rt.run_sh(
            str(self.case_dir),
            script,
            logfile=log_path.open("wb"),
        )

    # ---- single-node MPI ----

    def run_mpi(
        self,
        app: str,
        np: int,
        args: Sequence[str] | None = None,
        log_name: str | None = None,
        skip_if_exists: bool = True,
    ) -> None:
        """Run an MPI-enabled OpenFOAM utility on a single node.

        Reproduces bash `runMPI` from foam.bashrc:91.
        Uses np==1 fast path (no mpirun) when only one process requested.
        """
        args = args or []
        if log_name is None:
            log_name = f"log.{app}"
        log_path = self.case_dir / log_name
        if skip_if_exists and log_path.exists():
            rt.disp(f"Skipping MPI '{app}' (np={np}): log exists ({log_path})")
            return

        if np <= 1:
            # fast path: serial run, same as run_app
            script = app + (" " + " ".join(args) if args else "")
        else:
            # -parallel flag for OpenFOAM decomposed cases
            cmd_args = [*list(args), "-parallel"]
            script = (
                f"mpirun --mca btl self,vader -x LD_LIBRARY_PATH -x HWLOC_COMPONENTS -x MPI_BUFFER_SIZE -np {np} {app} "
                + " ".join(cmd_args)
            )

        rt.disp(f"Running MPI '{script}' > {log_name}")
        rt.run_sh(
            str(self.case_dir),
            script,
            logfile=log_path.open("wb"),
        )

    # ---- multi-node distributed MPI ----

    def run_distributed(
        self,
        app: str,
        np: int,
        args: Sequence[str] | None = None,
        hostfile: Path | str | None = None,
        log_name: str | None = None,
        skip_if_exists: bool = True,
    ) -> None:
        """Run an MPI-enabled OpenFOAM utility across multiple nodes.

        Reproduces bash `runDistributed` from foam.bashrc:121-126.
        """
        args = args or []
        if log_name is None:
            log_name = f"log.{app}"
        log_path = self.case_dir / log_name
        if skip_if_exists and log_path.exists():
            rt.disp(f"Skipping distributed '{app}' (np={np}): log exists ({log_path})")
            return

        if hostfile is None:
            msg = "run_distributed() requires a hostfile (no solver-specific default is assumed here)"
            raise ValueError(msg)

        cmd_args = [*list(args), "-parallel"]
        export_vars = "-x LD_LIBRARY_PATH -x HWLOC_COMPONENTS -x PATH -x WM_PROJECT_DIR -x WM_PROJECT_INST_DIR -x MPI_BUFFER_SIZE"
        script = f"mpirun.openmpi {export_vars} --mca btl_tcp_if_exclude lo,eth0:avahi --hostfile {hostfile} -np {np} {app} " + " ".join(cmd_args)

        rt.disp(f"Running distributed '{script}' > {log_name}")
        rt.run_sh(
            str(self.case_dir),
            script,
            logfile=log_path.open("wb"),
        )

    # ---- mesh topology utilities ----

    def decompose_par(self, np: int | None = None, skip_if_exists: bool = True) -> None:
        """Run decomposePar to split mesh into processor subdomains.

        Optionally overrides numberOfSubdomains in decomposeParDict first.
        """
        if np is not None:
            dict_path = self.case_dir / "system" / "decomposeParDict"
            if dict_path.exists():
                apply_edits(self.case_dir, [FileKV("system/decomposeParDict", "numberOfSubdomains", str(np))])
        self.run_app("decomposePar", skip_if_exists=skip_if_exists)

    def renumber_mesh(self, parallel: bool = False, np: int = 1, skip_if_exists: bool = True) -> None:
        """Run renumberMesh to improve mesh numbering for solver cache locality.

        If parallel=True, runs on decomposed case with -parallel flag.
        """
        args = ["-overwrite"]
        if parallel:
            self.run_mpi("renumberMesh", np, args, skip_if_exists=skip_if_exists)
        else:
            self.run_app("renumberMesh", args, skip_if_exists=skip_if_exists)

    def check_mesh(self, skip_if_exists: bool = True) -> None:
        """Run checkMesh."""
        self.run_app("checkMesh", skip_if_exists=skip_if_exists)

    def smooth_f_mesh(self, alpha: float, iterations: int, layers: int, vol_iso: int = 1) -> None:
        """Run smoothFMesh."""
        self.run_app("smoothFMesh", [str(alpha), str(iterations), str(layers), str(vol_iso)])

    def transform_points(self, scale_xyz: tuple[float, float, float]) -> None:
        """Run transformPoints -scale."""
        sx, sy, sz = scale_xyz
        self.run_app("transformPoints", ["-scale", f"'({sx} {sy} {sz})'"])

    # ---- dictionary editing ----

    def edit(self, edits: Sequence[FileKV] | FileKV) -> None:
        """Apply FileKV edits to case dictionary files.

        Delegates to foam_dict.apply_edits.
        """
        if isinstance(edits, FileKV):
            edits = [edits]
        apply_edits(self.case_dir, edits)

    # ---- log backup ----

    def backup_existing_log(self, app_name: str) -> Path | None:
        """Back up an existing log file to log.<app>-<timestamp>.

        Returns the new backup Path, or None if no log existed.
        """
        log_path = self.case_dir / f"log.{app_name}"
        if not log_path.exists():
            return None
        mtime = datetime.fromtimestamp(log_path.stat().st_mtime).strftime("%Y%m%d_%H%M%S")
        new_path = self.case_dir / f"log.{app_name}-{mtime}"
        log_path.rename(new_path)
        rt.disp(f"Backed up log.{app_name} -> {new_path.name}")
        return new_path

    # ---- run a utility in an explicit mode ----

    def run_mode(
        self,
        app: str,
        mode: str,
        np: int = 1,
        args: Sequence[str] | None = None,
        hostfile: Path | str | None = None,
        log_name: str | None = None,
        skip_if_exists: bool = True,
    ) -> None:
        """Run a utility in serial, parallel (MPI), or distributed (multi-node MPI) mode.

        Args:
            app: Utility executable name.
            mode: "distributed" -> run_distributed, "parallel" -> run_mpi, else -> run_app.
            np: Number of processes (ignored for serial).
            args: Extra CLI args.
            hostfile: Hostfile for distributed mode.
        """
        if mode == "distributed":
            self.run_distributed(app, np, args, hostfile=hostfile, log_name=log_name, skip_if_exists=skip_if_exists)
        elif mode == "parallel":
            self.run_mpi(app, np, args, log_name=log_name, skip_if_exists=skip_if_exists)
        else:
            self.run_app(app, args, log_name=log_name, skip_if_exists=skip_if_exists)

    # ---- convenience: run solver ----

    def run_solver(
        self,
        solver: str,
        parallel: bool = True,
        np: int = 1,
        hostfile: Path | str | None = None,
    ) -> None:
        """Run a solver, optionally via MPI.

        Args:
            solver: Solver executable name (e.g. 'interFaceFoam', 'icoNSFoam').
            parallel: If True, use MPI with `np` processes.
            np: Number of MPI processes.
            hostfile: For multi-node distributed runs.
        """
        self.backup_existing_log(solver)
        if not parallel or np <= 1:
            self.run_app(solver, skip_if_exists=False)
        elif hostfile is None:
            self.run_mpi(solver, np, skip_if_exists=False)
        else:
            self.run_distributed(solver, np, hostfile=hostfile, skip_if_exists=False)


def read_points_bbox(mesh_dir: Path | str) -> tuple[float, float, float, float, float, float]:
    """Read the bounding box from log.checkMesh or constant/polyMesh/points.

    Returns:
        (xmin, ymin, zmin, xmax, ymax, zmax)
    """
    mesh_dir = Path(mesh_dir)

    # 1. Check log.checkMesh first (fast, reliable, handles binary mesh without error).
    for candidate in (mesh_dir / "log.checkMesh", mesh_dir.parent / "log.checkMesh"):
        if candidate.exists():
            try:
                log_text = candidate.read_text(errors="ignore")
                m = re.search(
                    r"(?:Overall domain\s+)?bounding box\s*:?\s*\(\s*([^\)]+)\s*\)\s*\(\s*([^\)]+)\s*\)",
                    log_text,
                    re.IGNORECASE,
                )
                if m:
                    min_coords = [float(x) for x in m.group(1).split()]
                    max_coords = [float(x) for x in m.group(2).split()]
                    if len(min_coords) == 3 and len(max_coords) == 3:
                        return (
                            min_coords[0],
                            min_coords[1],
                            min_coords[2],
                            max_coords[0],
                            max_coords[1],
                            max_coords[2],
                        )
            except Exception:
                pass

    points_file = mesh_dir / "constant" / "polyMesh" / "points"
    if not points_file.exists():
        msg = f"points file not found at {points_file}"
        raise FileNotFoundError(msg)

    # 2. Try parsing ASCII points file directly.
    try:
        text = points_file.read_text()
        numbers = re.findall(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", text)
        floats = [float(n) for n in numbers]
        if len(floats) >= 6 and len(floats) % 3 == 0:
            xs = floats[0::3]
            ys = floats[1::3]
            zs = floats[2::3]
            return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
    except UnicodeDecodeError:
        pass

    # 3. If binary and no log.checkMesh yet, run checkMesh to extract bbox.
    case = FoamCase(mesh_dir)
    case.run_app("checkMesh", skip_if_exists=False)
    log_check = mesh_dir / "log.checkMesh"
    if log_check.exists():
        log_text = log_check.read_text(errors="ignore")
        m = re.search(
            r"(?:Overall domain\s+)?bounding box\s*:?\s*\(\s*([^\)]+)\s*\)\s*\(\s*([^\)]+)\s*\)",
            log_text,
            re.IGNORECASE,
        )
        if m:
            min_coords = [float(x) for x in m.group(1).split()]
            max_coords = [float(x) for x in m.group(2).split()]
            if len(min_coords) == 3 and len(max_coords) == 3:
                return (
                    min_coords[0],
                    min_coords[1],
                    min_coords[2],
                    max_coords[0],
                    max_coords[1],
                    max_coords[2],
                )

    msg = f"Could not determine bounding box for {mesh_dir}"
    raise ValueError(msg)


def darcy_flow_rate_from_bbox(
    bbox: tuple[float, float, float, float, float, float],
    darcy_velocity_um_s: float,
) -> float:
    """Compute volumetric flow rate from bounding box and Darcy velocity.

    Reproduces QOil/QWat computation from AllRunImageTwoPhase_spack:335-336.
    Area = (ymax - ymin) * (zmax - zmin) at the inlet face.
    Darcy velocity is in um/s; converts to m/s for SI flow rate (m³/s).
    """
    _, ymin, zmin, _, ymax, zmax = bbox
    area = (ymax - ymin) * (zmax - zmin)
    # darcy_velocity_um_s * 1e-6 = m/s
    return area * darcy_velocity_um_s * 1e-6


@dataclass
class MeshBuildResult:
    """Result of a GeometryBuilder.build() call."""

    case_dir: Path
    n_points: int = 0
    n_cells: int = 0
    n_faces: int = 0


class GeometryBuilder:
    """Protocol for mesh generation strategies.

    The generic layer defines only the interface; solver-specific geometry
    classes (e.g. SpackGeometry, VoxelImageGeometry, future gcfoam builders)
    implement this.
    """

    @abstractmethod
    def build(self, case: FoamCase, params: dict[str, Any]) -> MeshBuildResult:
        """Generate mesh in the given case directory.

        Args:
            case: The FoamCase whose directory should receive the mesh.
            params: Geometry-specific parameters (e.g. RSphere, RefineLevel).

        Returns:
            MeshBuildResult describing what was generated.
        """
        ...


# ---- CaseTemplateRunner: generic case setup base ----


class CaseTemplateRunner(ABC):
    """Base class for setting up OpenFOAM cases from a template.

    Generic workflow:
    1. Copy case template into a target (mesh/run) directory.
    2. Invoke a GeometryBuilder to generate the mesh.
    3. Apply a list of numerics/dict edits.
    4. Read bounding box from the mesh.

    Subclasses add solver-specific logic (contact angle, alpha field, etc.).
    """

    def __init__(
        self,
        template_dir: Path | str,
        geometry_builder: GeometryBuilder,
        work_dir: Path | str = Path.cwd(),
    ) -> None:
        self.template_dir = Path(template_dir)
        self.geometry_builder = geometry_builder
        self.work_dir = Path(work_dir)

    def _copy_template(self, target_name: str) -> Path:
        """Copy the case template to a new directory in work_dir."""
        target = self.work_dir / target_name
        rt.mkdr(str(target.parent))
        rt.run_sh(str(target.parent), f"cp -r {self.template_dir} {target}")
        return target

    def setup_mesh_case(
        self,
        target_name: str,
        geometry_params: dict[str, Any],
        numerics_edits: Sequence[FileKV] | None = None,
    ) -> FoamCase:
        """Set up a meshed case directory.

        Args:
            target_name: Name of the output directory (relative to work_dir).
            geometry_params: Parameters passed to GeometryBuilder.build().
            numerics_edits: Post-meshing dict edits (e.g. fvSolution tuning).

        Returns:
            FoamCase for the set-up directory, with mesh generated.
        """
        case_dir = self._copy_template(target_name)
        case = FoamCase(case_dir)
        rt.disp(f"########### Creating mesh: {target_name} ##########")
        self.geometry_builder.build(case, geometry_params)
        if numerics_edits:
            case.edit(numerics_edits)
        return case

    def read_bbox(self, case_dir: Path | str) -> tuple[float, float, float, float, float, float]:
        """Read bounding box from a meshed case directory."""
        return read_points_bbox(case_dir)
