from __future__ import annotations

from pathlib import Path
from typing import Any


def skelor(img=None, config=None, verbose: bool = False):
    """Extract pore network from a voxel image using skelor/snextract."""
    from .process import run_ske

    if verbose:
        print("Running Skelor network extraction")

    config = {} if config is None else config.copy()
    output_name = config.get("OutputName", config.get("name", "network"))
    overwrite_str = str(config.get("Overwrite", "T")).upper()
    force_run = overwrite_str in ("T", "TRUE", "1")

    if img is not None and hasattr(img, "write"):
        img.write(f"{output_name}.raw")

    kwrds = {k: v for k, v in config.items() if k not in ("OutputName", "name", "Overwrite")}
    ret = run_ske(kwrds=kwrds, bNam=output_name, resSuffix="", app="skelor", forceRun=force_run, resDir=".", netDir=".")
    return ret


def pnextract(img=None, config=None, verbose: bool = False):
    """
    Extract classical pore network from a voxel image using pnextract,
    or seed an existing network if NetworkSeed / SeedDir is specified.
    """
    from .network_ops import seed_net_to_xpm
    from .process import run_ske

    config = {} if config is None else config.copy()
    output_name = config.get("OutputName", config.get("name", "network"))
    overwrite_str = str(config.get("Overwrite", "T")).upper()
    force_run = overwrite_str in ("T", "TRUE", "1")

    seed_src = config.get("NetworkSeed", config.get("SeedDir", config.get("seed_dir", None)))
    if seed_src:
        if verbose:
            print(f"Seeding network from {seed_src}")
        target_dir = Path(config.get("netDir", "."))
        seed_net_to_xpm(seed_src, target_dir=target_dir, target_prefix=output_name)
        return 0

    if img is not None and hasattr(img, "write"):
        img.write(f"{output_name}.raw")

    kwrds = {k: v for k, v in config.items() if k not in ("OutputName", "name", "Overwrite")}
    ret = run_ske(kwrds=kwrds, bNam=output_name, resSuffix="", app="pnextract", forceRun=force_run, resDir=".", netDir=".")
    return ret


def scalor(config: dict[str, Any], verbose: bool = False):
    """Run snflow/scalor network flow simulation on a network file (.xmf)."""
    from .process import run_xnflow

    if verbose:
        print("Running Scalor")

    config = config.copy()
    network_file = config.get("NetworkFile", "")
    output_name = config.get("OutputName", config.get("name", "flow_simulation"))
    overwrite_str = str(config.get("Overwrite", "T")).upper()
    force_run = overwrite_str in ("T", "TRUE", "1")

    net_path = Path(network_file)
    net_dir = str(net_path.parent) if str(net_path.parent) != "" else "."
    net_stem = net_path.name
    for suffix in ("_ms.xmf", "_pn.xmf", ".xmf"):
        if net_stem.endswith(suffix):
            net_stem = net_stem[: -len(suffix)]
            break

    kwrds = {k: v for k, v in config.items() if k not in ("NetworkFile", "OutputName", "Overwrite")}
    kwrds["NetworkFile"] = str(net_path)
    kwrds["OutputName"] = output_name

    ret = run_xnflow(kwrds=kwrds, netnam=net_stem, resSuffix="", app="scalor", forceRun=force_run, resDir=".", netDir=net_dir)
    return ret


def cnflow(config: dict[str, Any], verbose: bool = False):
    """Run cnflow classical pore network simulation."""
    from .process import run_xnflow
    if verbose:
        print("Running Cnflow")
    config = config.copy()
    network_file = config.get("NetworkFile", "")
    network_base = config.get("NETWORK", "")
    output_name = config.get("OutputName", config.get("name", "cnflow_simulation"))
    overwrite_str = str(config.get("Overwrite", "T")).upper()
    force_run = overwrite_str in ("T", "TRUE", "1")

    if network_file:
        net_path = Path(network_file)
        net_dir = str(net_path.parent) if str(net_path.parent) != "" else "."
        net_stem = net_path.name
        for suffix in ("_link1.dat", "_node1.dat", "_ms.xmf", "_pn.xmf", ".xmf", ".mhd", ".dat"):
            if net_stem.endswith(suffix):
                net_stem = net_stem[: -len(suffix)]
                break
        kwrds = {k: v for k, v in config.items() if k not in ("NetworkFile", "OutputName", "Overwrite")}
        kwrds["NetworkFile"] = network_file
    elif network_base:
        net_stem = network_base.replace("F ", "").replace("T ", "").strip()
        net_dir = "."
        kwrds = {k: v for k, v in config.items() if k not in ("OutputName", "Overwrite")}
    else:
        net_stem = output_name
        net_dir = "."
        kwrds = {k: v for k, v in config.items() if k not in ("OutputName", "Overwrite")}

    kwrds["OutputName"] = output_name

    ret = run_xnflow(kwrds=kwrds, netnam=net_stem, resSuffix="", app="cnflow", forceRun=force_run, resDir=".", netDir=net_dir)
    return ret


def pnflow(config: dict[str, Any], verbose: bool = False, exe: str = "pnflow"):
    """Run pnflow classical pore network simulation."""
    from .process import run_xnflow

    config = config.copy()
    network_file = config.get("NetworkFile", "")
    network_base = config.get("NETWORK", "")
    output_name = config.get("OutputName", config.get("name", "pnflow_simulation"))
    overwrite_str = str(config.get("Overwrite", "T")).upper()
    force_run = overwrite_str in ("T", "TRUE", "1")

    if network_file:
        net_path = Path(network_file)
        net_dir = str(net_path.parent) if str(net_path.parent) != "" else "."
        net_stem = net_path.name
        for suffix in ("_link1.dat", "_node1.dat", "_ms.xmf", "_pn.xmf", ".xmf", ".mhd", ".dat"):
            if net_stem.endswith(suffix):
                net_stem = net_stem[: -len(suffix)]
                break
    elif network_base:
        net_stem = network_base.replace("F ", "").replace("T ", "").strip()
        net_dir = "."
    else:
        net_stem = output_name
        net_dir = "."

    kwrds = {k: v for k, v in config.items() if k not in ("NetworkFile", "OutputName", "Overwrite")}
    kwrds["NETWORK"] = f"F {net_stem}"
    kwrds["OutputName"] = output_name
    kwrds.pop("NetworkFile", None)

    ret = run_xnflow(kwrds=kwrds, netnam=net_stem, resSuffix="", app=exe, forceRun=force_run, resDir=".", netDir=net_dir)
    return ret


def xpm(config: dict[str, Any], verbose: bool = False):
    """Run XPM pore scale simulation directly on a voxel image or pre-seeded network."""
    from .xpm import run_xpm

    config = config.copy()
    output_name = config.get("OutputName", config.get("name", "xpm_simulation"))
    overwrite_str = str(config.get("Overwrite", "T")).upper()
    force_run = overwrite_str in ("T", "TRUE", "1")

    img_stem = output_name
    for key in ("ImageFile", "image", "NetworkSeed", "SeedDir", "seed_dir", "NetworkFile", "NETWORK"):
        val = str(config.get(key, ""))
        if val:
            img_stem = Path(val.replace("F ", "").strip()).stem
            for sfx in (".raw", ".raw.gz", ".mhd", "_ms", "_pn", "_link1", "_node1"):
                if img_stem.endswith(sfx):
                    img_stem = img_stem[: -len(sfx)]
            break

    ret = run_xpm(kwrds=config, netnam=img_stem, resSuffix="", forceRun=force_run, resDir=".", app="xpm")
    return ret
