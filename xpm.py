"""XPM wrappers"""
# FIXME: mostly vibe-coded, needs cleanup

from __future__ import annotations

import gzip
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from shutil import which
from typing import Any

from .process import mkdr
from .runtime import disp, msEnv, msInst

defaultnm = "snm"  # move to runtime.py and use in process.py to convert tsv to json if needed


def interpolate(x: float, x_points: list[float], y_points: list[float]) -> float:
    """Simple linear interpolation."""
    if not x_points:
        return 0.0
    if x <= x_points[0]:
        return y_points[0]
    if x >= x_points[-1]:
        return y_points[-1]

    for i in range(len(x_points) - 1):
        if x_points[i] <= x <= x_points[i + 1]:
            # Linear interpolation formula: y = y1 + (x - x1) * (y2 - y1) / (x2 - x1)
            dx = x_points[i + 1] - x_points[i]
            if dx == 0:
                return y_points[i]
            return y_points[i] + (x - x_points[i]) * (y_points[i + 1] - y_points[i]) / dx
    return 0.0


def read_res_file(file_path: str | Path) -> list[list[float]] | None:
    """Read a space/tab separated file into a list of lists."""
    data = []
    with Path(file_path).open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    data.append([float(x) for x in line.split()])
                except ValueError:
                    continue
    return data

def _get_ift_val(resDir, name):

    ift_val = 1.0
    config_candidates = [
        resDir / f"input_{name}_xpm.json",
        resDir / "config.json",
        resDir / "phi_k_kr_pc.json",
        Path.cwd() / f"input_{name}_xpm.json",
    ]
    for cfg_candidate in config_candidates:
        if cfg_candidate.exists():
            try:
                with cfg_candidate.open("r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                    if isinstance(cfg_data, dict):
                        if "network_model" in cfg_data and isinstance(cfg_data["network_model"], dict) and "interfacial_tension_n_per_m" in cfg_data["network_model"]:
                            ift_val = float(cfg_data["network_model"]["interfacial_tension_n_per_m"])
                            break
                        elif "macro" in cfg_data and isinstance(cfg_data["macro"], dict) and "interfacial_tension" in cfg_data["macro"]:
                            ift_val = float(cfg_data["macro"]["interfacial_tension"])
                            break
                        elif "physics_contract" in cfg_data and isinstance(cfg_data["physics_contract"], dict) and "interfacial_tension_si" in cfg_data["physics_contract"]:
                            ift_val = float(cfg_data["physics_contract"]["interfacial_tension_si"])
                            break
                        elif "interfacial_tension" in cfg_data:
                            ift_val = float(cfg_data["interfacial_tension"])
                            break
                        elif "WaterOil" in cfg_data:
                            ift_val = float(str(cfg_data["WaterOil"]).split()[0])
                            break
            except Exception:
                pass
    return ift_val

def xpm_json_to_snm_tsv(resDir: str | Path, name: str, ext: str = "_upscal.tsv") -> str:
    """
    Consolidate XPM JSON/TXT results into SNM TSV format.

    Args:
        resDir: Directory containing XPM results (pc_*.txt, kr_*.txt, etc.)
        name: Base name for the porous rock. Defaults to directory name.
        ext: Extension or suffix for the output file (e.g., '.tsv' or '_upscal.tsv').

    Returns:
        Path to the generated TSV file.
    """
    resDir = Path(resDir)
    resOutDir = resDir

    disp(f"Consolidating XPM results in {resDir.name}, name: {name}")

    # XPM puts results in results/<image_stem>/
    search_files = list(resDir.glob("**/phi_k_kr_pc.json"))
    if not search_files:
        raise FileNotFoundError(f"phi_k_kr_pc.json not found in {resDir}")
    matching = [p for p in search_files if p.parent.name.lower() in name.lower() or name.lower() in p.parent.name.lower()]
    target_file = matching[0] if matching else max(search_files, key=lambda p: p.stat().st_mtime)
    resDir = target_file.parent
    disp(f"  Found XPM result files in: {resDir.name}")

    # Metadata defaults
    poro = None
    perm = None

    # Try to read metadata from JSON
    for meta_name in ["phi_k_kr_pc.json", "petrophysics_summary.json"]:
        meta_json = resDir / meta_name
        assert meta_json.exists(), f"missing {Path.cwd()}/{meta_json}"
        try:
            with meta_json.open("r", encoding="utf-8") as f:
                m = json.load(f)
                if "poro" in m:
                    poro = m["poro"]
                elif "total_poro" in m:
                    poro = m["total_poro"]

                if "perm" in m:
                    perm = m["perm"]
                elif "total_perm" in m:
                    tp = m["total_perm"]
                    perm = tp[0] if isinstance(tp, list) else tp

        except (json.JSONDecodeError, KeyError, IndexError):
            continue

    assert poro is not None
    assert perm is not None
    output = []
    output.append(f"RockType:  {name}\n")
    output.append(f"{name}_porosity:           {poro} ;")
    # Convert permeability from mD to m^2 (* 1e-15)
    perm_m2 = perm * 1e-15
    output.append(f"{name}_permeability:       {perm_m2} ;")
    output.append(f"{name}_formationfactor:    {1.0 / poro if poro > 0 else 1.0} ;")

    ift_val = _get_ift_val(resDir, name)
    output.append(f"{name}_iftOW:              {ift_val} ;\n")

    # Cycles
    for cycle_idx, cycle in enumerate(["primary", "secondary"], 1):
        pc_file = resDir / f"pc_{cycle}.txt"
        kr_file = resDir / f"kr_{cycle}.txt"

        pc_data = read_res_file(pc_file) if pc_file.exists() else []
        kr_data = read_res_file(kr_file) if kr_file.exists() else []

        if len(pc_data) == 0 and len(kr_data) == 0:
            continue

        output.append(f"{name}_SwPcKrwKroRI_cycle{cycle_idx}:    // {cycle}")
        output.append("//Sw             Pc(Pa)          Krw             Kro                  RI")

        if len(pc_data) > 0:
            sw_pc = [row[0] for row in pc_data]
            pc_vals = [row[1] for row in pc_data]

            if len(kr_data) > 0:
                sw_kr = [row[0] for row in kr_data]
                krw_vals = [row[1] for row in kr_data]
                kro_vals = [row[2] for row in kr_data]

                # Resample kr data to pc Sw values
                for sw, pc in zip(sw_pc, pc_vals):
                    krw = interpolate(sw, sw_kr, krw_vals)
                    kro = interpolate(sw, sw_kr, kro_vals)
                    ri = 1.0  # Dummy for now
                    output.append(f"{sw:.6f}      {pc:.6e}    {krw:.6e}    {kro:.6e}    {ri:.6e}")
            else:
                # No kr data, use zeros
                for sw, pc in zip(sw_pc, pc_vals):
                    output.append(f"{sw:.6f}      {pc:.6e}    0.000000e+00    0.000000e+00    1.000000e+00")
        else:
            # We have kr_data but pc_data is empty; preserve kr_data points
            for row in kr_data:
                sw = row[0]
                krw = row[1] if len(row) > 1 else 0.0
                kro = row[2] if len(row) > 2 else 0.0
                pc = 0.0
                ri = 1.0
                output.append(f"{sw:.6f}      {pc:.6e}    {krw:.6e}    {kro:.6e}    {ri:.6e}")

        output.append("")  # Empty line between cycles

    content = "\n".join(output)
    out_file = f"{name}{ext}"
    out_path = resOutDir / out_file

    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"{content}\n")

    disp(f"  Created: {out_path}")

    return str(out_path)


def snm_to_xpm_json(kwrds: dict, imgName: str) -> dict:
    """Convert SNM keywords to XPM JSON configuration."""
    img_path = Path(imgName)
    stem = img_path.stem
    if stem.endswith(".raw"):
        stem = stem[:-4]

    img_size = None
    img_res = None

    # Check for accompanying .mhd header
    mhd_candidates = [
        img_path.with_suffix(".mhd"),
        Path(f"{imgName}.mhd"),
        img_path.parent / f"{stem}.mhd",
    ]
    for mhd in mhd_candidates:
        if mhd.is_file():
            try:
                for line in mhd.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("DimSize"):
                        img_size = [int(v) for v in line.split("=")[1].split()]
                    elif line.startswith("ElementSpacing") or line.startswith("ElementSize"):
                        img_res = float(line.split("=")[1].split()[0])
                if img_size and img_res:
                    break
            except Exception:
                pass

    if img_size is None:
        m_size = re.search(r"_(\d+)x(\d+)x(\d+)", stem)
        if m_size:
            img_size = [int(m_size.group(1)), int(m_size.group(2)), int(m_size.group(3))]
        else:
            img_size = kwrds.get("size", kwrds.get("DimSize", [0, 0, 0]))

    if img_res is None:
        m_res = re.search(r"_(\d+)p(\d*)um", stem)
        if m_res:
            res_str = f"{m_res.group(1)}.{m_res.group(2) or '0'}"
            img_res = float(res_str) * 1e-6
        else:
            img_res = float(kwrds.get("resolution", kwrds.get("voxel_size", 1e-6)))

    if not img_path.with_suffix(".raw").exists() and img_path.with_suffix(".raw.gz").exists():
        import gzip

        raw_target = img_path.with_suffix(".raw")
        with gzip.open(img_path.with_suffix(".raw.gz"), "rb") as f_in, raw_target.open("wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    resolved_img_path = str(img_path)
    if img_path.with_suffix(".raw").exists():
        resolved_img_path = str(img_path.with_suffix(".raw"))
    elif img_path.exists():
        resolved_img_path = str(img_path)

    void_v = int(kwrds.get("void", 0))
    solid_v = kwrds.get("solid", None)
    darcy_list = kwrds.get("darcy", None)

    if solid_v is None or darcy_list is None:
        sample_bytes = b""
        try:
            p_img = Path(resolved_img_path)
            if p_img.exists():
                sample_bytes = p_img.read_bytes()
        except Exception:
            pass

        if sample_bytes:
            unique_vals = sorted(set(sample_bytes))
            non_void = [v for v in unique_vals if v != void_v]
            if len(non_void) > 1 and darcy_list is None:
                bin_path = Path(resolved_img_path).with_name(f"{Path(resolved_img_path).stem}_bin.raw")
                arr = bytearray(sample_bytes)
                for i in range(len(arr)):
                    if arr[i] != void_v:
                        arr[i] = 1
                bin_path.write_bytes(arr)
                resolved_img_path = str(bin_path)
                solid_v = 1
            elif solid_v is None:
                solid_v = non_void[0] if non_void else 1
        else:
            if solid_v is None:
                solid_v = 1

    xpm = {
        "image": {
            "path": resolved_img_path,
            "size": img_size,
            "resolution": img_res,
            "phase": {"void": void_v, "solid": int(solid_v)},
        },
        "solver": {"decomposition": [1, 1, 1], "tolerance": 1e-6, "max_iterations": 1000},
        "report": {"display": "saturation", "invasion_percolation": True, "occupancy_images": False},
    }
    if darcy_list:
        xpm["darcy"] = darcy_list

    # 4. Map SNM keywords
    # Contact Angle
    ca_str = kwrds.get("AlterContAng", kwrds.get("InitContAng", ""))
    if ca_str:
        parts = ca_str.split()
        if len(parts) >= 3:
            try:
                avg_ca = (float(parts[1]) + float(parts[2])) / 2.0
                xpm.setdefault("macro", {})["contact_angle"] = avg_ca
            except ValueError:
                pass

    # Interfacial tension
    ift = kwrds.get("WaterOil", kwrds.get("interfacial_tension", None))
    if ift is not None:
        try:
            ift_val = float(str(ift).split()[0])
            xpm.setdefault("macro", {})["interfacial_tension"] = ift_val
            if "network_model" in xpm and isinstance(xpm["network_model"], dict):
                xpm["network_model"]["interfacial_tension_n_per_m"] = ift_val
        except (ValueError, IndexError):
            pass

    # Saturation steps and capillary pressure limits
    cycle1_str = kwrds.get("Cycle1", "")
    if cycle1_str:
        parts = cycle1_str.split()
        if len(parts) >= 2:
            try:
                max_pc = float(parts[1])
                if max_pc > 0:
                    xpm.setdefault("report", {})["max_capillary_pressure"] = max_pc
            except ValueError:
                pass
        if len(parts) >= 3:
            try:
                del_sw = float(parts[2])
                if del_sw > 0:
                    xpm.setdefault("report", {})["capillary_pressure_sw_step"] = del_sw
                    xpm.setdefault("report", {})["relative_permeability_sw_step"] = del_sw
            except ValueError:
                pass

    for k in ("capillary_pressure_sw_step", "sw_step", "delSw"):
        if k in kwrds:
            xpm.setdefault("report", {})["capillary_pressure_sw_step"] = float(kwrds[k])
    for k in ("relative_permeability_sw_step", "kr_sw_step", "delSw"):
        if k in kwrds:
            xpm.setdefault("report", {})["relative_permeability_sw_step"] = float(kwrds[k])
    for k in ("max_capillary_pressure", "maxPc"):
        if k in kwrds:
            xpm.setdefault("report", {})["max_capillary_pressure"] = float(kwrds[k])

    if "network_model" in kwrds and isinstance(kwrds["network_model"], dict):
        xpm["network_model"] = kwrds["network_model"]
        if ift is not None:
            try:
                xpm["network_model"]["interfacial_tension_n_per_m"] = float(str(ift).split()[0])
            except (ValueError, IndexError):
                pass

    # Darcy (microporous) properties: only include if there is actual microporous content.
    # A purely binary image (void/solid) has no darcy phase and must not include this block,
    # because an empty `cap_press` curve causes xpm to crash with a segfault.
    # SNM keywords don't currently expose microporous info so we leave it out by default.
    # TODO: add support for microporous phases from SNM keywords if needed.

    return xpm


def run_xpm(kwrds: dict[str, Any] | None = None, netnam: str = "", forceRun: bool = False, resDir: str = "./resultsXPM", app: str = "xpm", **kwargs) -> int:
    """
    Expose xpm via subprocess.Popen.

    Args:
        kwrds: Dictionary of parameters for xpm.
        config: Path to the JSON configuration file or network name.
        forceRun: Whether to force re-running the simulation.
        resDir: Directory for simulation results and logs.
        app: Path to the xpm executable.
        **kwargs: Additional arguments like resSuffix and netDir.

    Returns:
        The return code of the xpm process.
    """
    if kwrds is None:
        kwrds = {}

    resSuffix = kwargs.get("resSuffix", "")
    if resDir and resDir.endswith("/"):
        resDir = resDir[:-1]

    output_name = kwrds.get("OutputName", kwrds.get("name", ""))
    if output_name:
        name = output_name
    else:
        name = Path(netnam).stem + resSuffix
    log_name = f"{name}_{app}.log"
    lognam = Path(resDir or ".") / log_name

    if forceRun or not lognam.exists():
        mkdr(resDir)

        # Convert kwrds to a config.json file
        config_path = Path(resDir) / f"input_{name}_xpm.json"
        disp(f"Converting SNM keywords to XPM config: {Path.cwd()}/{config_path}")

        netDir = kwargs.get("netDir", ".")
        img_abs_dir = (Path(netDir) / f"{Path(netnam).stem}.raw").resolve()
        xpm_kwrds = snm_to_xpm_json(kwrds, imgName=str(img_abs_dir))

        with Path(config_path).open("w", encoding="utf-8") as f:
            json.dump(xpm_kwrds, f, indent=4)

        log_path = Path(lognam).resolve()
        # Use relative path for config if it's inside resDir
        config_run = Path(config_path).name

        with log_path.open("ab") as logfile:
            path_env = msEnv.get("PATH", "")

            app_abs = app
            if not Path(app).is_absolute():
                app_abs = which(app, path=path_env)
                assert app_abs, f"{app} not found on PATH (checked {msInst} and PATH={path_env})"

            (Path(resDir) / "pnextract").mkdir(exist_ok=True)

            myenv = msEnv.copy()
            myenv["HWLOC_COMPONENTS"] = "-opencl"

            disp(f"\n\nRunning {app_abs} -G {config_run} in {resDir} > {log_path}")
            sys.stdout.flush()
            sys.stderr.flush()
            proc = subprocess.Popen(
                [app_abs, "-G", config_run],
                stdout=logfile,
                stderr=subprocess.STDOUT,
                cwd=resDir,
                env=myenv,
            )
            proc.wait()

            assert proc.returncode == 0, f"xpm failed, see stdout and {log_path}"

            if defaultnm == "snm":
                xpm_json_to_snm_tsv(resDir, name=name)  # , ext="_upscal.tsv"
                tsv_path = Path(resDir) / f"{name}_upscal.tsv"
                assert tsv_path.exists(), f"{Path.cwd()}/{tsv_path} not created"

    disp(f"Skipping {app}, {lognam} exists.")
    return 0


def xpm_json_to_mhd(config_path, ske_dir) -> Path:
    with Path(config_path).open("r") as f:
        config = json.load(f)

    assert "image" in config, f"image not found in {config_path}"

    img_info = config["image"]
    img_rel_path = img_info.get("path")
    assert img_rel_path, f"image/path not found in {config_path}"

    img_stem = Path(img_rel_path).stem

    if img_stem.endswith(".raw"):  # strip .raw.gz
        img_stem = img_stem[:-4]

    # Find the actual .raw file
    raw_path = None

    # 1. Try relative to config file
    p = (config_path.parent / img_rel_path).resolve()
    if p.exists():
        shutil.copy(p, ske_dir)
        with p.open("rb") as f_in, gzip.open(ske_dir / (f"{p.name}.gz"), "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    # 2. Try searching in common roots
    elif Path(str(p).replace(".raw", ".tar.gz")).exists():
        tar_path = Path(str(p).replace(".raw", ".tar.gz"))
        with tarfile.open(tar_path) as f:
            if hasattr(tarfile, "data_filter"):
                f.extractall(path=ske_dir, filter="data")
            else:
                f.extractall(path=ske_dir)
        extracted_raw = ske_dir / p.name
        with Path(extracted_raw).open("rb") as f_in, gzip.open(ske_dir / (f"{p.name}.gz"), "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    raw_path = ske_dir / (f"{p.name}.gz")
    assert raw_path.exists(), f"image file not found: {p.name}"

    # res: resolution in meters
    res = img_info.get("resolution", 1.0)
    size = img_info.get("size", [0, 0, 0])

    mhd_path = ske_dir / f"{img_stem}.mhd"

    mhd_content = [
        "ObjectType = Image",
        "NDims = 3",
        "BinaryData = True",
        "BinaryDataByteOrderMSB = False",
        "CompressedData = True",
        "Offset = 0 0 0",
        f"ElementSpacing = {res} {res} {res}",
        f"DimSize = {size[0]} {size[1]} {size[2]}",
        "ElementType = MET_UCHAR",
        f"ElementDataFile = {img_stem}.raw.gz",
    ]

    with Path(mhd_path).open("w") as f:
        content = "\n".join(mhd_content)
        f.write(f"{content}\n")

    return mhd_path
