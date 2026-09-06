"""Pore network operations, geometry transformations, and artifact seeding."""

from __future__ import annotations

import math
import os
import re
import shutil
import struct
from pathlib import Path
from typing import Any, Callable

import numpy as np

# Exact shape factor for equilateral triangle: G = sqrt(3) / 36
EQUILATERAL_SHAPE_FACTOR: float = math.sqrt(3.0) / 36.0  # ~0.048112522432468815

# Exact shape factor for square: G = 1 / 16
SQUARE_SHAPE_FACTOR: float = 1.0 / 16.0  # 0.0625

# Exact shape factor for circle: G = 1 / (4 * pi)
CIRCLE_SHAPE_FACTOR: float = 1.0 / (4.0 * math.pi)  # ~0.07957747154594767

CORE_NETWORK_SUFFIXES: tuple[str, ...] = ("_link1.dat", "_link2.dat", "_node1.dat", "_node2.dat")
AUXILIARY_NETWORK_SUFFIXES: tuple[str, ...] = ("_VElems.raw", "_VElems.mhd", "_network.complete")
ALL_NETWORK_SUFFIXES: tuple[str, ...] = CORE_NETWORK_SUFFIXES + AUXILIARY_NETWORK_SUFFIXES


def modify_network_throats(
    link1_path: str | Path,
    transform_fn: Callable[[list[str]], list[str]],
) -> None:
    """Read _link1.dat throat table, apply transform_fn to column tokens of each throat, and rewrite."""
    path = Path(link1_path)
    if not path.is_file():
        return

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return

    new_lines = [lines[0]]  # Header line: throat count
    for line in lines[1:]:
        tokens = line.split()
        if not tokens:
            continue
        transformed = transform_fn(tokens)
        new_lines.append("     " + " ".join(transformed))

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def modify_network_pores(
    node2_path: str | Path,
    transform_fn: Callable[[list[str]], list[str]],
) -> None:
    """Read _node2.dat pore table, apply transform_fn to column tokens of each pore, and rewrite."""
    path = Path(node2_path)
    if not path.is_file():
        return

    lines = path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    for line in lines:
        tokens = line.split()
        if not tokens:
            continue
        transformed = transform_fn(tokens)
        new_lines.append("     " + " ".join(transformed))

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def set_network_shape_factor(
    prefix_or_dir: str | Path,
    shape_factor: float = EQUILATERAL_SHAPE_FACTOR,
) -> None:
    """
    Set cross-sectional shape factor G in _link1.dat and _node2.dat.

    In _link1.dat, shape factor is in column index 4 (0-indexed):
      id  node1 node2 radius shape_factor total_length ...

    In _node2.dat, shape factor is in column index 3 (0-indexed):
      id volume radius shape_factor ...
    """
    p = Path(prefix_or_dir)
    if p.is_dir():
        link1_cands = list(p.glob("*_link1.dat"))
        node2_cands = list(p.glob("*_node2.dat"))
        if not link1_cands or not node2_cands:
            msg = f"Could not locate _link1.dat and _node2.dat in {p}"
            raise FileNotFoundError(msg)
        link1_path = link1_cands[0]
        node2_path = node2_cands[0]
    else:
        prefix = str(p)
        link1_path = Path(f"{prefix}_link1.dat")
        node2_path = Path(f"{prefix}_node2.dat")

    g_str = f"{shape_factor:.6E}"

    def _set_throat_g(tokens: list[str]) -> list[str]:
        if len(tokens) > 4:
            tokens[4] = g_str
        return tokens

    def _set_pore_g(tokens: list[str]) -> list[str]:
        if len(tokens) > 3:
            tokens[3] = g_str
        return tokens

    modify_network_throats(link1_path, _set_throat_g)
    modify_network_pores(node2_path, _set_pore_g)


def set_network_equilateral(prefix_or_dir: str | Path) -> None:
    """Set shape factor to equilateral triangle (G = sqrt(3)/36 ~ 0.0481125)."""
    set_network_shape_factor(prefix_or_dir, EQUILATERAL_SHAPE_FACTOR)


def find_network_files(
    source: str | Path,
    prefix: str | None = None,
) -> tuple[Path, str, dict[str, Path]]:
    """
    Find network files in directory or from a file path prefix.

    Returns:
        (directory, detected_prefix, matched_files_dict)
    """
    source_p = Path(source).resolve()

    candidate_dirs: list[Path] = []
    candidate_prefixes: list[str] = []

    if source_p.is_dir():
        candidate_dirs.append(source_p)
        if prefix:
            candidate_prefixes.append(prefix)
        else:
            for item in source_p.iterdir():
                if item.is_file() and item.name.endswith("_link1.dat"):
                    pfx = item.name[: -len("_link1.dat")]
                    if pfx not in candidate_prefixes:
                        candidate_prefixes.append(pfx)
            if "" not in candidate_prefixes:
                candidate_prefixes.append("")
    else:
        candidate_dirs.append(source_p.parent)
        stem = source_p.name
        for sfx in ALL_NETWORK_SUFFIXES:
            if stem.endswith(sfx):
                stem = stem[: -len(sfx)]
                break
        candidate_prefixes.append(stem)

    for c_dir in candidate_dirs:
        for pfx in candidate_prefixes:
            matched: dict[str, Path] = {}
            for sfx in ALL_NETWORK_SUFFIXES:
                fname = f"{pfx}{sfx}"
                candidate_f = c_dir / fname
                if candidate_f.is_file():
                    matched[sfx] = candidate_f

            if all(core_sfx in matched for core_sfx in CORE_NETWORK_SUFFIXES):
                return c_dir, pfx, matched

    msg = f"Could not find core network files ({', '.join(CORE_NETWORK_SUFFIXES)}) in {source_p} (checked prefixes: {candidate_prefixes})"
    raise FileNotFoundError(msg)


def seed_net_to_xpm(
    source: str | Path,
    target_dir: str | Path = ".",
    target_prefix: str = "",
    source_prefix: str | None = None,
    mode: str = "copy",
    overwrite: bool = True,
    synthesize_velems: bool = False,
    image_size: tuple[int, int, int] | list[int] | None = None,
) -> dict[str, Path]:
    """
    Seed (stage) pore network artifacts from a source into an XPM target directory.

    Stages the required network files (_link1.dat, _link2.dat, _node1.dat, _node2.dat,
    and optional _VElems.raw) so that XPM detects cached pnextract output and skips extraction.
    """
    _source_dir, _det_prefix, matched_source = find_network_files(source, prefix=source_prefix)

    target_path = Path(target_dir).resolve()
    target_path.mkdir(parents=True, exist_ok=True)

    seeded_files: dict[str, Path] = {}

    def _place_file(src: Path, dst: Path) -> None:
        if dst.exists():
            if not overwrite:
                return
            dst.unlink()

        if mode == "link":
            try:
                os.link(src, dst)
                return
            except OSError:
                pass
        elif mode == "symlink":
            try:
                os.symlink(src, dst)
                return
            except OSError:
                pass

        shutil.copy2(src, dst)

    for sfx in ALL_NETWORK_SUFFIXES:
        if sfx in matched_source:
            key = sfx.lstrip("_").replace(".dat", "").replace(".raw", "")
            dst = target_path / f"{target_prefix}{sfx}"
            _place_file(matched_source[sfx], dst)
            seeded_files[key] = dst

    if synthesize_velems and "_VElems.raw" not in matched_source and image_size is not None:
        nx, ny, nz = int(image_size[0]), int(image_size[1]), int(image_size[2])
        expected_bytes = (nx + 2) * (ny + 2) * (nz + 2) * 4
        velems_dst = target_path / f"{target_prefix}_VElems.raw"
        if not velems_dst.exists() or (overwrite and velems_dst.stat().st_size != expected_bytes):
            with velems_dst.open("wb") as f:
                chunk = b"\x00" * 65536
                written = 0
                while written < expected_bytes:
                    to_write = min(expected_bytes - written, len(chunk))
                    f.write(chunk[:to_write])
                    written += to_write
            seeded_files["VElems"] = velems_dst

    return seeded_files


def read_xpm_invasion_entry_file(path: str | Path) -> dict[str, Any]:
    """
    Read an XPM binary invasion entry file (invasion_entry_rc_primary.bin or invasion_entry_rc_secondary.bin).

    Binary format:
      Header (24 bytes, little-endian):
        - magic (uint32): 0x31455249 ('IRE1')
        - version (uint32): 1
        - cycle (uint32): 0 (primary) or 1 (secondary)
        - reserved (uint32): 0
        - element_count (uint64): total pores + throats
      Payload:
        - r_cap (float32 array of length element_count):
          Critical capillary invasion radius in meters. Elements not invaded have r_cap = 0.0.

    Returns:
      dict with 'magic', 'version', 'cycle', 'element_count', 'r_cap'.
    """
    path = Path(path)
    if not path.is_file():
        msg = f"Invasion entry file not found: {path}"
        raise FileNotFoundError(msg)

    with path.open("rb") as f:
        magic, version, cycle, _reserved, element_count = struct.unpack("<IIIIQ", f.read(24))
        if magic != 0x31455249:
            msg = f"Invalid magic number in {path}: {hex(magic)} (expected 0x31455249)"
            raise ValueError(msg)
        r_cap = np.fromfile(f, dtype=np.float32, count=element_count)

    return {
        "magic": magic,
        "version": version,
        "cycle": cycle,
        "element_count": element_count,
        "r_cap": r_cap,
    }


def get_xpm_invasion_entry_pressures(
    entry_path_or_dir: str | Path,
    cycle: str = "primary",
    sigma: float = 1.0,
    pore_count: int | None = None,
) -> dict[str, Any]:
    """
    Parse invasion entry file and compute capillary entry/snap-off pressures (Pc = sigma / r_cap).

    Args:
        entry_path_or_dir: Path to invasion_entry_rc_*.bin file, or results directory.
        cycle: 'primary' or 'secondary' if a directory is specified.
        sigma: Interfacial tension in N/m (default 1.0, so Pc = 1 / r_cap).
        pore_count: If provided, separates pores (0..pore_count-1) and throats (pore_count..end).

    Returns:
        dict with 'r_cap', 'pc', 'invaded_mask', and optional 'pore_pc', 'throat_pc'.
    """
    p = Path(entry_path_or_dir)
    if p.is_dir():
        filename = f"invasion_entry_rc_{cycle}.bin"
        cand = list(p.glob(f"**/{filename}"))
        if not cand:
            msg = f"Could not find {filename} in {p}"
            raise FileNotFoundError(msg)
        p = cand[0]

    data = read_xpm_invasion_entry_file(p)
    r_cap = data["r_cap"]
    invaded = r_cap > 0.0
    pc = np.zeros_like(r_cap)
    pc[invaded] = sigma / r_cap[invaded]

    res = {
        "cycle": data["cycle"],
        "element_count": data["element_count"],
        "r_cap": r_cap,
        "pc": pc,
        "invaded_mask": invaded,
    }
    if pore_count is not None:
        res["pore_r_cap"] = r_cap[:pore_count]
        res["pore_pc"] = pc[:pore_count]
        res["throat_r_cap"] = r_cap[pore_count:]
        res["throat_pc"] = pc[pore_count:]

    return res


def get_network_radii_statistics(prefix_or_dir: str | Path) -> dict[str, Any]:
    """
    Extract pore and throat radii statistics (mean, min, max, count) from _link1.dat and _node2.dat.

    Returns:
        dict with keys: 'num_pores', 'pore_r_mean', 'pore_r_min', 'pore_r_max',
                        'num_throats', 'throat_r_mean', 'throat_r_min', 'throat_r_max'.
    """
    p = Path(prefix_or_dir)
    if p.is_dir():
        link1_cands = list(p.glob("*_link1.dat"))
        node2_cands = list(p.glob("*_node2.dat"))
        if not link1_cands or not node2_cands:
            msg = f"Could not locate _link1.dat and _node2.dat in {p}"
            raise FileNotFoundError(msg)
        link1_path = link1_cands[0]
        node2_path = node2_cands[0]
    else:
        prefix = str(p)
        link1_path = Path(f"{prefix}_link1.dat")
        node2_path = Path(f"{prefix}_node2.dat")

    t_radii: list[float] = []
    if link1_path.is_file():
        with link1_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines[1:]:
                parts = line.strip().split()
                if len(parts) >= 4:
                    t_radii.append(float(parts[3]))

    p_radii: list[float] = []
    if node2_path.is_file():
        with node2_path.open("r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 3:
                    p_radii.append(float(parts[2]))

    return {
        "num_pores": len(p_radii),
        "pore_r_mean": sum(p_radii) / len(p_radii) if p_radii else 0.0,
        "pore_r_min": min(p_radii) if p_radii else 0.0,
        "pore_r_max": max(p_radii) if p_radii else 0.0,
        "num_throats": len(t_radii),
        "throat_r_mean": sum(t_radii) / len(t_radii) if t_radii else 0.0,
        "throat_r_min": min(t_radii) if t_radii else 0.0,
        "throat_r_max": max(t_radii) if t_radii else 0.0,
    }


def format_radii_stats_table(stats: dict[str, Any], title: str = "NETWORK GEOMETRY: ELEMENT RADII STATISTICS") -> str:
    """Format a clean markdown/text table for pore and throat radii statistics."""
    lines = [
        "=" * 80,
        title,
        "=" * 80,
        f"{'Element Type':<16} {'Count':<10} {'Mean Radius (m)':<20} {'Min Radius (m)':<18} {'Max Radius (m)':<18}",
        "-" * 80,
        f"{'Pores':<16} {stats['num_pores']:<10} {stats['pore_r_mean']:<20.4e} {stats['pore_r_min']:<18.4e} {stats['pore_r_max']:<18.4e}",
        f"{'Throats':<16} {stats['num_throats']:<10} {stats['throat_r_mean']:<20.4e} {stats['throat_r_min']:<18.4e} {stats['throat_r_max']:<18.4e}",
        "=" * 80,
    ]
    return "\n".join(lines)


def load_xpm_network_statistics(res_dir_or_path: str | Path) -> dict[str, Any] | None:
    """Load network_stats.json generated by XPM."""
    import json

    p = Path(res_dir_or_path)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    cands = list(p.glob("**/network_stats.json"))
    if cands:
        return json.loads(cands[0].read_text(encoding="utf-8"))
    return None


def format_radii_comparison_table(
    cnm_stats: dict[str, Any],
    xpm_stats: dict[str, Any] | None = None,
    title: str = "PORE AND THROAT RADII COMPARISON: CNM vs XPM",
) -> str:
    """Format a side-by-side comparison table between CNM network and XPM internal network stats."""
    if xpm_stats is None:
        return format_radii_stats_table(cnm_stats, title=title)

    def _diff_pct(val_xp: float, val_cn: float) -> float:
        if val_cn == 0:
            return 0.0
        return 100.0 * (val_xp - val_cn) / val_cn

    diff_pore_mean = _diff_pct(xpm_stats.get("pore_r_mean", 0.0), cnm_stats["pore_r_mean"])
    diff_pore_min = _diff_pct(xpm_stats.get("pore_r_min", 0.0), cnm_stats["pore_r_min"])
    diff_pore_max = _diff_pct(xpm_stats.get("pore_r_max", 0.0), cnm_stats["pore_r_max"])
    diff_throat_mean = _diff_pct(xpm_stats.get("throat_r_mean", 0.0), cnm_stats["throat_r_mean"])
    diff_throat_min = _diff_pct(xpm_stats.get("throat_r_min", 0.0), cnm_stats["throat_r_min"])
    diff_throat_max = _diff_pct(xpm_stats.get("throat_r_max", 0.0), cnm_stats["throat_r_max"])

    pore_cnt_match = "0.0%" if cnm_stats["num_pores"] == xpm_stats.get("num_pores") else "MISMATCH"
    throat_cnt_match = "0.0%" if cnm_stats["num_throats"] == xpm_stats.get("num_throats") else "MISMATCH"

    lines = [
        "=" * 80,
        title,
        "=" * 80,
        f"{'Metric':<26} {'CNFLOW (Net)':<16} {'XPM (Internal)':<16} {'Diff (%)':<12}",
        "-" * 80,
        f"{'Pore Count':<26} {cnm_stats['num_pores']:<16} {xpm_stats.get('num_pores', '-'):<16} {pore_cnt_match:<12}",
        f"{'Mean Pore Radius (m)':<26} {cnm_stats['pore_r_mean']:<16.4e} {xpm_stats.get('pore_r_mean', 0.0):<16.4e} {diff_pore_mean:+.4f}%",
        f"{'Min Pore Radius (m)':<26} {cnm_stats['pore_r_min']:<16.4e} {xpm_stats.get('pore_r_min', 0.0):<16.4e} {diff_pore_min:+.4f}%",
        f"{'Max Pore Radius (m)':<26} {cnm_stats['pore_r_max']:<16.4e} {xpm_stats.get('pore_r_max', 0.0):<16.4e} {diff_pore_max:+.4f}%",
        "-" * 80,
        f"{'Throat Count':<26} {cnm_stats['num_throats']:<16} {xpm_stats.get('num_throats', '-'):<16} {throat_cnt_match:<12}",
        f"{'Mean Throat Radius (m)':<26} {cnm_stats['throat_r_mean']:<16.4e} {xpm_stats.get('throat_r_mean', 0.0):<16.4e} {diff_throat_mean:+.4f}%",
        f"{'Min Throat Radius (m)':<26} {cnm_stats['throat_r_min']:<16.4e} {xpm_stats.get('throat_r_min', 0.0):<16.4e} {diff_throat_min:+.4f}%",
        f"{'Max Throat Radius (m)':<26} {cnm_stats['throat_r_max']:<16.4e} {xpm_stats.get('throat_r_max', 0.0):<16.4e} {diff_throat_max:+.4f}%",
        "=" * 80,
    ]
    return "\n".join(lines)


def format_multi_ca_table(
    ca_results: list[dict[str, Any]],
    title: str = "IMBIBITION SECONDARY CYCLE: MIDDLE THROAT PRESSURES ACROSS CONTACT ANGLES",
    has_analytical: bool = False,
) -> str:
    """Format a comparison table for imbibition snap-off Pc across multiple contact angles.

    Supports both middle-throat reporting (when 'mid_mech' is present in rows)
    and legacy analytical/mean comparison formats.
    """
    if any("mid_mech" in r for r in ca_results):
        table_width = 80
        lines = [
            "=" * table_width,
            title,
            "=" * table_width,
            f"{'Theta':<12} {'Mechanism':<16} {'CNM Mid (Pa)':<18} {'XPM Mid (Pa)':<18} {'Diff CN vs XP':<14}",
            "-" * table_width,
        ]
        for row in ca_results:
            th = f"{row['theta']:.1f} deg"
            mech = str(row.get("mid_mech", "-"))
            cn_mid = f"{row['mid_pc_cn']:<18.4e}"
            xp_mid = f"{row['mid_pc_xp']:<18.4e}"
            diff_m_s = f"{row['diff_mid_pct']:+.4f}%" if mech != "Cutoff (None)" and abs(row.get("mid_pc_cn", 0.0)) > 1e-3 else "~0 Pa"
            lines.append(f"{th:<12} {mech:<16} {cn_mid} {xp_mid} {diff_m_s:<14}")
        lines.append("=" * table_width)
        return "\n".join(lines)

    lines = [
        "=" * 80,
        title,
        "=" * 80,
    ]
    if has_analytical:
        lines.append(f"{'Theta (deg)':<14} {'Analytical (Pa)':<18} {'CNFLOW (Pa)':<16} {'XPM (Pa)':<16} {'Diff CN vs XP':<14}")
        lines.append("-" * 80)
        for row in ca_results:
            th = f"{row['theta']:.1f} deg"
            ana = f"{row['pc_snap_ana']:<18.4e}"
            cn = f"{row['pc_snap_cn']:<16.4e}"
            xp = f"{row['pc_snap_xp']:<16.4e}"
            diff = f"{row['diff_snap_pct']:+.4f}%" if (abs(row.get("pc_snap_ana", 1.0)) > 1e-3 and abs(row["pc_snap_cn"]) > 1e-3) else "~0 Pa"
            lines.append(f"{th:<14} {ana} {cn} {xp} {diff:<14}")
    else:
        lines.append(f"{'Theta (deg)':<14} {'CNFLOW Mean (Pa)':<18} {'XPM Mean (Pa)':<18} {'Diff CN vs XP':<14}")
        lines.append("-" * 80)
        for row in ca_results:
            th = f"{row['theta']:.1f} deg"
            cn = f"{row['mean_pc_snap_cn']:<18.4e}"
            xp = f"{row['mean_pc_snap_xp']:<18.4e}"
            diff = f"{row['diff_snap_pct']:+.3f}%" if abs(row["mean_pc_snap_cn"]) > 1e-3 else "~0 Pa"
            lines.append(f"{th:<14} {cn} {xp} {diff:<14}")
    lines.append("=" * 80)
    return "\n".join(lines)


def parse_cnm_corner_angle_statistics(cnflow_log: str) -> dict[str, float]:
    """Parse corner half-angle and corner number statistics from CNFLOW log.

    CNFLOW logs all angles in radians. This function converts them directly to degrees.
    """
    stats: dict[str, float] = {}
    for line in cnflow_log.splitlines():
        # Matches: hAngPore: <arith> <vw> [<min> <max>]
        m_hang = re.search(
            r"(hAngPore|hAngThroat|hAngElem):\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)(?:\s+([0-9.eE+-]+)\s+([0-9.eE+-]+))?",
            line,
        )
        if m_hang:
            key = m_hang.group(1)
            arith_rad = float(m_hang.group(2))
            vw_rad = float(m_hang.group(3))
            min_rad = float(m_hang.group(4)) if m_hang.group(4) is not None else arith_rad
            max_rad = float(m_hang.group(5)) if m_hang.group(5) is not None else arith_rad
            entity = "pore" if "Pore" in key else ("throat" if "Throat" in key else "elem")
            stats[f"{entity}_half_ang_arith_deg"] = math.degrees(arith_rad)
            stats[f"{entity}_half_ang_vw_deg"] = math.degrees(vw_rad)
            stats[f"{entity}_half_ang_min_deg"] = math.degrees(min_rad)
            stats[f"{entity}_half_ang_max_deg"] = math.degrees(max_rad)
            stats[f"{entity}_full_ang_arith_deg"] = 2.0 * math.degrees(arith_rad)
            stats[f"{entity}_full_ang_vw_deg"] = 2.0 * math.degrees(vw_rad)
            stats[f"{entity}_full_ang_min_deg"] = 2.0 * math.degrees(min_rad)
            stats[f"{entity}_full_ang_max_deg"] = 2.0 * math.degrees(max_rad)

        m_ncor = re.search(r"(NcorPore|NcorThroat|NcorElem):\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)", line)
        if m_ncor:
            key = m_ncor.group(1)
            arith_n = float(m_ncor.group(2))
            vw_n = float(m_ncor.group(3))
            entity = "pore" if "Pore" in key else ("throat" if "Throat" in key else "elem")
            stats[f"{entity}_n_corners"] = arith_n
            stats[f"{entity}_vw_n_corners"] = vw_n

    return stats


def format_corner_angle_table(
    stats: dict[str, float],
    title: str = "CNM NETWORK: CORNER ANGLE STATISTICS (DEGREES)",
) -> str:
    """Format CNFLOW corner angle statistics as a simplified table in degrees."""
    lines = [
        "=" * 80,
        title,
        "=" * 80,
        f"{'Metric':<38} {'Pores':<20} {'Throats':<20}",
        "-" * 80,
    ]
    if "pore_n_corners" in stats and "throat_n_corners" in stats:
        lines.append(f"{'Corners per Element':<38} {stats['pore_n_corners']:<20.1f} {stats['throat_n_corners']:<20.1f}")

    p_fmean = f"{stats.get('pore_full_ang_arith_deg', 0.0):.2f}°"
    t_fmean = f"{stats.get('throat_full_ang_arith_deg', 0.0):.2f}°"
    lines.append(f"{'Mean Corner Angle (2*beta)':<38} {p_fmean:<20} {t_fmean:<20}")

    p_fmin = f"{stats.get('pore_full_ang_min_deg', 0.0):.2f}°"
    t_fmin = f"{stats.get('throat_full_ang_min_deg', 0.0):.2f}°"
    lines.append(f"{'Min Corner Angle (2*beta)':<38} {p_fmin:<20} {t_fmin:<20}")

    p_fmax = f"{stats.get('pore_full_ang_max_deg', 0.0):.2f}°"
    t_fmax = f"{stats.get('throat_full_ang_max_deg', 0.0):.2f}°"
    lines.append(f"{'Max Corner Angle (2*beta)':<38} {p_fmax:<20} {t_fmax:<20}")

    if "pore_full_ang_vw_deg" in stats and "throat_full_ang_vw_deg" in stats:
        p_fvw = f"{stats['pore_full_ang_vw_deg']:.2f}°"
        t_fvw = f"{stats['throat_full_ang_vw_deg']:.2f}°"
        lines.append(f"{'Vol-Weighted Corner Angle (2*beta)':<38} {p_fvw:<20} {t_fvw:<20}")

    lines.append("=" * 80)
    return "\n".join(lines)
