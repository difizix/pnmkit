"""XPM wrappers"""
# FIXME: mostly vibe-coded, needs cleanup

from __future__ import annotations

import contextlib
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

from .process import mkdr, which
from .runtime import disp, msEnv, MS_INST

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


def _get_ift_val(resDir: str | Path, name: str) -> float:
    ift_val = 1.0
    resDir = Path(resDir)
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
                        if (
                            "network_model" in cfg_data
                            and isinstance(cfg_data["network_model"], dict)
                            and "interfacial_tension_n_per_m" in cfg_data["network_model"]
                        ):
                            ift_val = float(cfg_data["network_model"]["interfacial_tension_n_per_m"])
                            break
                        if "macro" in cfg_data and isinstance(cfg_data["macro"], dict) and "interfacial_tension" in cfg_data["macro"]:
                            ift_val = float(cfg_data["macro"]["interfacial_tension"])
                            break
                        if (
                            "physics_contract" in cfg_data
                            and isinstance(cfg_data["physics_contract"], dict)
                            and "interfacial_tension_si" in cfg_data["physics_contract"]
                        ):
                            ift_val = float(cfg_data["physics_contract"]["interfacial_tension_si"])
                            break
                        if "interfacial_tension" in cfg_data:
                            ift_val = float(cfg_data["interfacial_tension"])
                            break
                        if "WaterOil" in cfg_data:
                            ift_val = float(str(cfg_data["WaterOil"]).split()[0])
                            break
            except Exception:
                pass
    return ift_val


def xpm_json_to_snm_tsv(resDir: str | Path, name: str, ext: str = "_upscal.tsv") -> str:
    """Consolidate XPM JSON/TXT results into SNM TSV format."""
    resDir = Path(resDir)
    resOutDir = resDir

    disp(f"Consolidating XPM results in {resDir.name}, name: {name}")

    # Check for network_stats.json if present
    stats_file = resDir / "network_stats.json"
    if not stats_file.is_file():
        cand_files = list(resDir.glob("**/network_stats.json"))
        if cand_files:
            stats_file = cand_files[0]

    # XPM puts results in results/<image_stem>/
    search_files = list(resDir.glob("**/phi_k_kr_pc.json"))
    if not search_files:
        msg = f"phi_k_kr_pc.json not found in {resDir}"
        raise FileNotFoundError(msg)
    matching = [p for p in search_files if p.parent.name.lower() in name.lower() or name.lower() in p.parent.name.lower()]
    target_file = matching[0] if matching else max(search_files, key=lambda p: p.stat().st_mtime)
    resDir = target_file.parent
    disp(f"  Found XPM result files in: {resDir.name}")

    poro = None
    perm = None

    for meta_name in ["phi_k_kr_pc.json", "petrophysics_summary.json"]:
        meta_json = resDir / meta_name
        if meta_json.exists():
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

    if poro is None and stats_file.is_file():
        try:
            with open(stats_file) as f:
                sdata = json.load(f)
                poro = float(sdata.get("porosity", sdata.get("poro", 0.0)))
                perm = float(sdata.get("permeability", sdata.get("perm", 0.0))) * 1e15
        except Exception:
            pass

    assert poro is not None, f"Could not determine porosity in {resDir}"
    assert perm is not None, f"Could not determine permeability in {resDir}"

    output = []
    output.append(f"RockType:  {name}\n")
    output.append(f"{name}_porosity:           {poro} ;")
    perm_m2 = perm * 1e-15
    output.append(f"{name}_permeability:       {perm_m2} ;")
    output.append(f"{name}_formationfactor:    {1.0 / poro if poro > 0 else 1.0} ;")

    ift_val = _get_ift_val(resOutDir, name)
    output.append(f"{name}_iftOW:              {ift_val} ;\n")

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

                for sw, pc in zip(sw_pc, pc_vals):
                    krw = interpolate(sw, sw_kr, krw_vals)
                    kro = interpolate(sw, sw_kr, kro_vals)
                    ri = 1.0
                    output.append(f"{sw:.6f}      {pc:.6e}    {krw:.6e}    {kro:.6e}    {ri:.6e}")
            else:
                for sw, pc in zip(sw_pc, pc_vals):
                    output.append(f"{sw:.6f}      {pc:.6e}    0.000000e+00    0.000000e+00    1.000000e+00")
        else:
            for row in kr_data:
                sw = row[0]
                krw = row[1] if len(row) > 1 else 0.0
                kro = row[2] if len(row) > 2 else 0.0
                pc = 0.0
                ri = 1.0
                output.append(f"{sw:.6f}      {pc:.6e}    {krw:.6e}    {kro:.6e}    {ri:.6e}")

        output.append("")

    content = "\n".join(output)
    out_file = f"{name}{ext}"
    out_path = resOutDir / out_file

    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"{content}\n")

    disp(f"  Created: {out_path}")
    if resOutDir != Path():
        with contextlib.suppress(Exception):
            shutil.copy(out_path, Path(out_file))

    return str(out_path)


def snm_to_xpm_json(kwrds: dict, imgName: str) -> dict:
    """Convert SNM keywords to XPM JSON configuration."""
    img_path = Path(imgName)
    stem = img_path.stem
    stem = stem.removesuffix(".raw")

    img_size = None
    img_res = None

    mhd_candidates = [
        img_path.with_suffix(".mhd"),
        Path(f"{imgName}.mhd"),
        img_path.parent / f"{stem}.mhd",
    ]
    if "ImageFile" in kwrds:
        p = Path(kwrds["ImageFile"])
        if p.is_file():
            mhd_candidates.insert(0, p)
        if p.with_suffix(".mhd").is_file():
            mhd_candidates.insert(0, p.with_suffix(".mhd"))

    for mhd in mhd_candidates:
        if mhd.is_file():
            try:
                for line in mhd.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("DimSize"):
                        img_size = [int(v) for v in line.split("=")[1].split()]
                    elif line.startswith(("ElementSpacing", "ElementSize")):
                        img_res = float(line.split("=")[1].split()[0])
                if img_size and img_res:
                    break
            except Exception:
                pass

    if img_size is None:
        siz = re.search(r"_(\d+)x(\d+)x(\d+)", stem)
        img_size = [int(siz.group(1)), int(siz.group(2)), int(siz.group(3))] if siz else kwrds.get("size", kwrds.get("DimSize", [0, 0, 0]))

    if img_res is None:
        m_res = re.search(r"_(\d+)p(\d*)um", stem)
        if m_res:
            res_str = f"{m_res.group(1)}.{m_res.group(2) or '0'}"
            img_res = float(res_str) * 1e-6
        else:
            img_res = float(kwrds.get("resolution", kwrds.get("voxel_size", 1e-6)))

    if not img_path.with_suffix(".raw").exists() and img_path.with_suffix(".raw.gz").exists():
        raw_target = img_path.with_suffix(".raw")
        with gzip.open(img_path.with_suffix(".raw.gz"), "rb") as f_in, raw_target.open("wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    resolved_img_path = str(img_path)
    if img_path.with_suffix(".raw").exists():
        resolved_img_path = str(img_path.with_suffix(".raw"))
    elif img_path.exists():
        resolved_img_path = str(img_path)

    void_v = int(kwrds.get("void", 0))
    solid_v = kwrds.get("solid")
    darcy_list = kwrds.get("darcy")

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
        elif solid_v is None:
            solid_v = 1

    xpm_cfg = {
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
        xpm_cfg["darcy"] = darcy_list

    ca_str = kwrds.get("AlterContAng", kwrds.get("InitContAng", ""))
    if ca_str:
        parts = ca_str.split()
        if len(parts) >= 3:
            try:
                avg_ca = (float(parts[1]) + float(parts[2])) / 2.0
                xpm_cfg.setdefault("macro", {})["contact_angle"] = avg_ca
            except ValueError:
                pass
        elif len(parts) == 1:
            with contextlib.suppress(ValueError):
                xpm_cfg.setdefault("macro", {})["contact_angle"] = float(parts[0])

    ift = kwrds.get("WaterOil", kwrds.get("interfacial_tension"))
    if ift is not None:
        try:
            ift_val = float(str(ift).split()[0])
            xpm_cfg.setdefault("macro", {})["interfacial_tension"] = ift_val
            if "network_model" in xpm_cfg and isinstance(xpm_cfg["network_model"], dict):
                xpm_cfg["network_model"]["interfacial_tension_n_per_m"] = ift_val
        except (ValueError, IndexError):
            pass

    cycle1_str = kwrds.get("Cycle1", "")
    if cycle1_str:
        parts = cycle1_str.split()
        if len(parts) >= 2:
            try:
                max_pc = float(parts[1])
                if max_pc > 0:
                    xpm_cfg.setdefault("report", {})["max_capillary_pressure"] = max_pc
            except ValueError:
                pass
        if len(parts) >= 3:
            try:
                del_sw = float(parts[2])
                if del_sw > 0:
                    xpm_cfg.setdefault("report", {})["capillary_pressure_sw_step"] = del_sw
                    xpm_cfg.setdefault("report", {})["relative_permeability_sw_step"] = del_sw
            except ValueError:
                pass

    for k in ("capillary_pressure_sw_step", "sw_step", "delSw"):
        if k in kwrds:
            xpm_cfg.setdefault("report", {})["capillary_pressure_sw_step"] = float(kwrds[k])
    for k in ("relative_permeability_sw_step", "kr_sw_step", "delSw"):
        if k in kwrds:
            xpm_cfg.setdefault("report", {})["relative_permeability_sw_step"] = float(kwrds[k])
    for k in ("max_capillary_pressure", "maxPc"):
        if k in kwrds:
            xpm_cfg.setdefault("report", {})["max_capillary_pressure"] = float(kwrds[k])

    if "network_model" in kwrds and isinstance(kwrds["network_model"], dict):
        xpm_cfg["network_model"] = kwrds["network_model"]
        if ift is not None:
            with contextlib.suppress(ValueError, IndexError):
                xpm_cfg["network_model"]["interfacial_tension_n_per_m"] = float(str(ift).split()[0])

    return xpm_cfg


def run_xpm(kwrds: dict[str, Any] | None = None, netnam: str = "", forceRun: bool = False, resDir: str = "./", app: str = "xpm", **kwargs) -> int:
    """Run an XPM simulation using parameters from a dictionary or SNM keywords."""
    if kwrds is None:
        kwrds = {}
    kwrds = kwrds.copy()
    kwrds.update(kwargs)
    extra_env = kwrds.pop("extra_env", None) or kwargs.pop("extra_env", None)

    if resDir and resDir.endswith("/"):
        resDir = resDir[:-1]

    name = kwrds.get("OutputName", kwrds.get("name", netnam if netnam else "xpm_sim"))
    log_name = f"{name}_{app}.log"
    log_path = Path(resDir or ".") / log_name
    config_run = f"input_{name}_xpm.json"

    if forceRun or not log_path.is_file():
        mkdr(resDir)

        config_path = Path(resDir) / config_run
        disp(f"Converting SNM keywords to XPM config: {Path.cwd()}/{config_path}")

        img_file = kwrds.get("ImageFile", kwrds.get("image", ""))
        if img_file:
            p_img = Path(img_file)
            img_abs_dir = p_img.with_suffix(".raw").resolve() if p_img.suffix in [".mhd", ".raw", ".raw.gz"] else p_img.resolve()
        else:
            netDir = kwargs.get("netDir", ".")
            img_abs_dir = (Path(netDir) / f"{Path(netnam).stem}.raw").resolve()

        xpm_kwrds = snm_to_xpm_json(kwrds, imgName=str(img_abs_dir))

        with Path(config_path).open("w", encoding="utf-8") as f:
            json.dump(xpm_kwrds, f, indent=4)

        lognam = log_path
        with Path(lognam).open("wb") as logfile:
            disp(f"// -*- JSON -*- run_xpm, ls:\n{config_path}\n")

            ms_bin = str(Path(MS_INST) / "bin") if MS_INST else ""
            path_env = f"{ms_bin}:{msEnv.get('PATH', '')}" if ms_bin else msEnv.get("PATH", "")

            app_abs = app
            if not Path(app).is_absolute():
                app_abs = which(app, path=path_env)
                assert app_abs, f"{app} not found on PATH (checked {MS_INST} and PATH={path_env})"

            (Path(resDir) / "pnextract").mkdir(exist_ok=True)

            myenv = msEnv.copy()
            myenv.update(os.environ)
            myenv["HWLOC_COMPONENTS"] = "-opencl"
            if extra_env:
                myenv.update(extra_env)

            seed_src = kwrds.get("NetworkSeed", kwrds.get("SeedDir", kwrds.get("seed_dir", None)))
            net_spec = seed_src or kwrds.get("NETWORK", kwrds.get("NetworkFile", kwrds.get("NetworkPrefix", kwrds.get("NetworkDir", netnam))))
            if not net_spec and img_file:
                stem = Path(img_file).stem
                if (Path.cwd() / f"{stem}_link1.dat").exists() or (Path.cwd() / f"{stem}_node1.dat").exists():
                    net_spec = stem

            if net_spec:
                parts = str(net_spec).split()
                raw_target = parts[1] if (len(parts) > 1 and parts[0] in ("F", "B")) else parts[0]
                target_p = Path(raw_target)
                if target_p.is_file():
                    seed_dir = target_p.parent.resolve()
                    prefix = target_p.stem.replace("_link1", "").replace("_node1", "")
                elif target_p.is_dir():
                    seed_dir = target_p.resolve()
                    prefix = ""
                else:
                    netDir = Path(kwargs.get("netDir", ".")).resolve()
                    seed_dir = netDir
                    prefix = raw_target

                try:
                    img_size = xpm_kwrds.get("image", {}).get("size") if isinstance(xpm_kwrds, dict) else None
                    from .network_ops import seed_net_to_xpm

                    pnextract_dir = Path(resDir) / "pnextract"
                    stem = Path(img_abs_dir).stem if img_abs_dir else ""
                    if stem:
                        seed_net_to_xpm(
                            seed_dir,
                            target_dir=pnextract_dir / stem,
                            target_prefix="",
                            source_prefix=prefix if prefix else None,
                            synthesize_velems=True,
                            image_size=img_size,
                        )
                    seed_net_to_xpm(
                        seed_dir,
                        target_dir=pnextract_dir,
                        target_prefix="",
                        source_prefix=prefix if prefix else None,
                        synthesize_velems=True,
                        image_size=img_size,
                    )
                except Exception as e:
                    disp(f"Notice: Python-side network staging: {e}")

                myenv["XPM_PNEXTRACT_SEED_DIR"] = str(seed_dir)

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

            if Path(resDir) != Path():
                with contextlib.suppress(Exception):
                    shutil.copy(log_path, Path(log_name))

            if defaultnm == "snm":
                xpm_json_to_snm_tsv(resDir, name=name)
                tsv_path = Path(resDir) / f"{name}_upscal.tsv"
                assert tsv_path.exists(), f"{Path.cwd()}/{tsv_path} not created"

    disp(f"Skipping {app}, {lognam} exists.")
    return 0


def xpm_json_to_mhd(config_path, ske_dir) -> Path:
    """Generate an MHD header file corresponding to an XPM JSON configuration."""
    with Path(config_path).open("r") as f:
        config = json.load(f)

    assert "image" in config, f"image not found in {config_path}"

    img_info = config["image"]
    img_rel_path = img_info.get("path")
    assert img_rel_path, f"image/path not found in {config_path}"

    img_stem = Path(img_rel_path).stem

    img_stem = img_stem.removesuffix(".raw")

    raw_path = None
    p = (Path(config_path).parent / img_rel_path).resolve()
    if p.exists():
        shutil.copy(p, ske_dir)
        with p.open("rb") as f_in, gzip.open(Path(ske_dir) / f"{p.name}.gz", "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    elif Path(str(p).replace(".raw", ".tar.gz")).exists():
        tar_path = Path(str(p).replace(".raw", ".tar.gz"))
        with tarfile.open(tar_path) as f:
            if hasattr(tarfile, "data_filter"):
                f.extractall(path=ske_dir, filter="data")
            else:
                f.extractall(path=ske_dir)
        extracted_raw = Path(ske_dir) / p.name
        with Path(extracted_raw).open("rb") as f_in, gzip.open(Path(ske_dir) / f"{p.name}.gz", "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    raw_path = Path(ske_dir) / f"{p.name}.gz"
    assert raw_path.exists(), f"image file not found: {p.name}"

    res = img_info.get("resolution", 1.0)
    size = img_info.get("size", [0, 0, 0])
    mhd_path = Path(ske_dir) / f"{img_stem}.mhd"

    mhd_content = [
        "ObjectType = Image",
        "NDims = 3",
        "BinaryData = True",
        "BinaryDataByteOrderMSB = False",
        "CompressedData = True",
        "Offset = 0 0 0",
        f"ElementSize = {res} {res} {res}",
        f"DimSize = {size[0]} {size[1]} {size[2]}",
        "ElementType = MET_UCHAR",
        f"ElementDataFile = {img_stem}.raw.gz",
    ]

    with Path(mhd_path).open("w") as f:
        content = "\n".join(mhd_content)
        f.write(f"{content}\n")

    return mhd_path
