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

from .msrc import disp, msEnv, msInst
from .msutils import mkdr

defaultnm = "snm" # move to msrc.py and use in msutils.py to convert tsv to json if needed

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


def xpm_json_to_snm_tsv(
    resDir: str | Path,
    name: str,
    ext: str = "_upscal.tsv"
) -> str:
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

    # XPM usually puts results in a subdirectory: results/<image_stem>/
    # We search for phi_k_kr_pc.json recursively to find the actual results dir
    search_files = list(resDir.glob("**/phi_k_kr_pc.json"))
    assert len(search_files) == 1, f"not sure which is xpm output, len>1 for: {search_files}"
    if search_files:
        # Pick the one that is most likely the right one (closest to name or just the first)
        resDir = search_files[0].parent
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
    output.append(f"{name}_permeability:       {perm} ;")
    output.append(f"{name}_formationfactor:    {1.0 / poro if poro > 0 else 1.0} ;")
    output.append(f"{name}_iftOW:              0.05 ;\n")

    # Cycles
    for cycle_idx, cycle in enumerate(["primary", "secondary"], 1):
        pc_file = resDir / f"pc_{cycle}.txt"
        kr_file = resDir / f"kr_{cycle}.txt"

        if not pc_file.exists():
            print(f"Warning: missing {pc_file}")
            continue

        pc_data = read_res_file(pc_file)
        if len(pc_data) == 0:
            continue

        output.append(f"{name}_SwPcKrwKroRI_cycle{cycle_idx}:    // {cycle}")
        output.append("//Sw             Pc(Pa)          Krw             Kro                  RI")

        sw_pc = [row[0] for row in pc_data]
        pc_vals = [row[1] for row in pc_data]

        kr_data = read_res_file(kr_file)
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

    # Extract base name (remove known SNM network extensions)

    # 1. Basic Structure with defaults
    xpm = {
        "image": {
            "path": imgName,
            "phase": {"void": 0, "solid": 255}
            # size # set below
            # resolution # set below
        },
        "solver": {
            "decomposition": [1, 1, 1],
            "tolerance": 1e-6,
            "max_iterations": 1000
        },
        "report": {
            "display": "saturation",
            "invasion_percolation": True
        }
    }

    stem = Path(imgName).stem  # e.g. "TPak2DExtruded_240x200x28_5p0um"

    # Guess image size from filename: _<NX>x<NY>x<NZ>
    m_size = re.search(r"_(\d+)x(\d+)x(\d+)", stem)
    if m_size:
        xpm["image"]["size"] = [int(m_size.group(1)), int(m_size.group(2)), int(m_size.group(3))]
    else:
        xpm["image"]["size"] = [0, 0, 0]
        disp(f"  Warning: Could not parse image size from '{imgName}', using defaults.")

    # Guess resolution from filename: _<N>p<M>um  (e.g. _5p0um => 5.0 um => 5e-6 m)
    m_res = re.search(r"_(\d+)p(\d*)um", stem)
    if m_res:
        res_str = f"{m_res.group(1)}.{m_res.group(2) or '0'}"
        xpm["image"]["resolution"] = float(res_str) * 1e-6
    else:
        xpm["image"]["resolution"] = 1e-6
        disp(f"  Warning: Could not parse resolution from '{imgName}', using 1 um default.")

    # 4. Map SNM keywords
    # Contact Angle
    ca_str = kwrds.get("AlterContAng", "")
    if ca_str:
        parts = ca_str.split()
        if len(parts) >= 3:
            try:
                avg_ca = (float(parts[1]) + float(parts[2])) / 2.0
                xpm.setdefault("macro", {})["contact_angle"] = avg_ca
            except ValueError:
                pass

    # Darcy (microporous) properties: only include if there is actual microporous content.
    # A purely binary image (void/solid) has no darcy phase and must not include this block,
    # because an empty `cap_press` curve causes xpm to crash with a segfault.
    # SNM keywords don't currently expose microporous info so we leave it out by default.
    # TODO: add support for microporous phases from SNM keywords if needed.

    return xpm


def runXPM(
    kwrds: dict[str, Any] | None = None,
    netnam: str = "",
    forceRun: bool = False,
    resDir: str = "./resultsXPM",
    app: str = "xpm",
    **kwargs
) -> int:
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
                app_abs = which(app, path=path_env) or app

            (Path(resDir) / "pnextract").mkdir(exist_ok=True)

            myenv = msEnv.copy()
            assert (Path(msInst)/"bin/xpm").exists(), f"xpm not found in {msInst}/bin"

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
                xpm_json_to_snm_tsv(resDir, name=name)  #, ext="_upscal.tsv"
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
        f"ElementDataFile = {img_stem}.raw.gz"
    ]

    with Path(mhd_path).open("w") as f:
        content = "\n".join(mhd_content)
        f.write(f"{content}\n")

    return mhd_path
