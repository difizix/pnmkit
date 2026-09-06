"""Synthetic triangular prism benchmark integration tests (triu).

Procedural geometry: Triangular prism with sinusoidal inscribed radius.
Executables tested: skelor (mextract), pnextract, scalor (snflow), cnflow, xpm.
Can be executed via pytest or directly as a standalone benchmark script:
    python3 pnmkit/tests/test_synthetic_triu.py

Contact Angle Implementation Status in CNFLOW (cnm) vs XPM:
------------------------------------------------------------

1. XPM:
   - Does NOT natively support Morrow empirical hysteresis models (Model 3 or Model 4).
   - Contact angles are specified via two configurations:
     * Macro mode ('macro.contact_angle'): Single uniform contact angle in degrees, applied
       to both primary and secondary cycles (zero hysteresis, theta_adv = theta_rec = theta).
     * Network model wettability ('network_model.wettability.populations'): Explicitly specifies
       receding and advancing angles ('reference_phase_receding_deg', 'reference_phase_advancing_deg').
   - Physics mechanism: Implements geometric contact-line pinning and hinging hysteresis:
     During corner film formation in drainage, films form at receding angle theta_rec. In imbibition,
     the contact line remains pinned at distance d = r_cap * cos(theta_rec + beta) / sin(beta) while
     Pc decreases, causing the contact angle to hinge according to:
     cos(theta_hinge + beta) = d * sin(beta) / r_cap.
     Once theta_hinge reaches the advancing angle theta_adv, the contact line unpins and advances.
   - Using Morrow Models 3 or 4 in XPM requires evaluating the Morrow relation externally
     (e.g., in pnmkit) to compute the (theta_rec, theta_adv) bounds, then passing them into XPM.

2. CNFLOW (cnm):
   - Accepts contact angle keywords:
     * 'InitContAng': sets initial contact angles during primary drainage (Cycle 1).
     * 'AlterContAng': alters contact angles for water injection / imbibition (Cycle 2).
   - Implements five contact angle hysteresis models via VoidElem::setContactAngle (polygon.cpp):
     * Model 1 (Morrow Model 1): Zero hysteresis (theta_adv = theta_rec = theta_ref). Advancing
       and receding contact angles are identical to the input contact angle.
     * Model 2: Linear hysteresis model parameterized by separation angle DAng (CAMdl2SepAng):
       growthExp = (pi + DAng) / pi; theta_rec = max(0, growthExp * theta_e - DAng);
       theta_adv = min(pi, growthExp * theta_e).
     * Model 3: Morrow (1975) empirical hysteresis model based on intrinsic / equilibrium
       contact angle theta_e (refCAng), using piecewise exponential and linear fits to Morrow's
       experimental advancing and receding curves for smooth surfaces.
     * Model 4: Morrow (1975) empirical model where the input parameter is directly the advancing
       contact angle (theta_adv = theta_ref), and receding contact angle theta_rec is derived via:
       theta_rec = [pi - 1.3834263 - (pi - theta_adv + 0.004)^0.45]^(1/0.45) - 0.004.
     * Model 5: Generalized empirical power-law correlation with separation parameter DAng.
   - Additional features:
     * Fractional wettability (FracContOpt) for mixed-wet systems.
     * Contact angle correlations (CACrl): 'rMax', 'rMin', 'rand', 'const'.

Physical & Percolation Pitfalls in Pore-Scale Benchmarking:
----------------------------------------------------------
1. Pore-Scale Element Matching vs Network-Wide Averaging:
   - In 2-pore 3-throat serial systems (Inlet -> Pore 1/2 -> Throat 2 -> Pore 2/1 -> Outlet),
     the middle throat (Throat 2, index 1) is the canonical unconstrained internal constriction.
   - For direct 1:1 pore-scale validation against Mayer-Stowe-Princen (MSP) theory, the internal
     middle throat must be compared directly.

2. Boundary Piston Invasion Pitfall:
   - Outer boundary throats (Throats 1 and 3) connect directly to inlet and outlet reservoirs.
   - During secondary imbibition (wetting phase injection), wetting fluid directly invades boundary
     throats from the inlet by frontal piston displacement at pressures dictated by reservoir access,
     rather than via corner meniscus swelling and snap-off.
   - Averaging boundary throats with internal throats mixes piston entry with snap-off cutoffs,
     producing large apparent network-average discrepancies.

3. Percolation Access Choking Pitfall:
   - In dynamic invasion percolation, entry into an element is constrained by upstream choke points.
   - If an element is preceded by a narrower constriction, its dynamic entry pressure reflects the
     upstream choke threshold rather than its local unconstrained geometric entry threshold.

4. Equilateral Triangle Snap-off Cutoff:
   - For equilateral triangular cross-sections, corner half-angles are beta = 30 deg.
   - Corner meniscus growth and snap-off physically require theta < 90 deg - beta = 60 deg.
   - At theta >= 60 deg, corner menisci cannot swell and snap-off is completely suppressed
     (Pc_snap <= 0).
"""

from __future__ import annotations

import math
import os
import re
import shutil
from pathlib import Path
from typing import Any

from pnmkit import cnflow, pnextract, xpm
from pnmkit.network_ops import (
    format_corner_angle_table,
    format_multi_ca_table,
    format_radii_comparison_table,
    get_network_radii_statistics,
    get_xpm_invasion_entry_pressures,
    load_xpm_network_statistics,
    parse_cnm_corner_angle_statistics,
    set_network_equilateral,
)
from pnmkit.runtime import grab_scalar as findf
from pnmkit.runtime import msEnv


def _has_exe(app: str) -> bool:
    """Check if the given executable is found in msEnv PATH or system PATH."""
    return shutil.which(app, path=msEnv.get("PATH", "")) is not None


def _make_tringu_image(target_dir: Path):
    """Generate the synthetic triangular prism image."""
    try:
        import image3kit
    except ImportError as exc:
        msg = "image3kit is required to generate synthetic images"
        raise ImportError(msg) from exc
    VxlImgU8 = image3kit.VxlImgU8
    triangular = image3kit.triangular
    dbl3 = image3kit.dbl3

    img = VxlImgU8((120, 30, 33), 1)
    # c_rp_rt=4.0 (Rp/Rt_mid=4), c_side_mid=1.6 (Rt_side=1.6*Rt_mid, wider boundary throats)
    img.paint(triangular((0, 28, 16), L1=15, L2=15, h=18, Lt=30, c_rp_rt=3.2, c_side_mid=1.6, val=0))
    img.spacing = dbl3(5e-7, 5e-7, 5e-7)

    target_dir.mkdir(parents=True, exist_ok=True)
    mhd_path = target_dir / "tringu.mhd"
    img.write(str(mhd_path))

    img.plot_slice(filename=str(target_dir / "tringu_xy"), normal_axis="z")
    img.plot_slice(filename=str(target_dir / "tringu_yz"), normal_axis="x")

    return img, mhd_path


def parse_cnm_pc_debug(log_text: str) -> tuple[dict[int, float], dict[int, float]]:
    """Extract entry and snap-off pressures from CNM_DEBUG_PC log lines."""
    drainage_pc: dict[int, float] = {}
    imbibition_snap: dict[int, float] = {}
    for line in log_text.splitlines():
        if "[CNM_DEBUG_PC]" not in line:
            continue
        if "stage=drainage" in line:
            m = re.search(r"Throat\s+(\d+).*?Pc_piston=([0-9.eE+-]+)", line)
            if m:
                drainage_pc[int(m.group(1))] = float(m.group(2))
        elif "stage=imbibition" in line:
            m = re.search(r"Throat\s+(\d+).*?Pc_snap=([0-9.eE+-]+)", line)
            if m:
                imbibition_snap[int(m.group(1))] = float(m.group(2))
    return drainage_pc, imbibition_snap


def calculate_analytical_equilateral_pc(r_ins: float, theta_deg: float = 0.0, sigma: float = 1.0) -> tuple[float, float]:
    """Calculate analytical Mayer-Stowe-Princen entry and snap-off Pc for equilateral triangle."""
    beta = math.pi / 6.0
    theta = math.radians(theta_deg)
    G = math.sqrt(3.0) / 36.0
    cos_th = math.cos(theta)
    if cos_th > 0:
        D = 3.0 * (math.pi / 2.0 - cos_th * math.cos(theta + beta) / math.sin(beta) - theta - beta)
        r_cap_piston = r_ins / (1.0 + math.sqrt(max(0.0, 1.0 + 4.0 * G * D / (cos_th**2)))) / cos_th
        pc_entry = sigma / r_cap_piston
    else:
        pc_entry = 0.0

    denom = math.cos(theta) - math.sin(theta) / math.sqrt(3.0)
    if denom > 1e-12:
        r_cap_snap = r_ins / denom
        pc_snap = sigma / r_cap_snap
    else:
        pc_snap = 0.0
    return pc_entry, pc_snap


def run_triu_benchmark(
    target_dir: Path | str | None = None,
    sigma: float = 1.0,
    contact_angles: tuple[float, ...] = (0.0, 30.0, 60.0),
    verbose: bool = True,
) -> dict[str, Any]:
    """Execute complete triangular prism benchmark comparing CNM and XPM."""
    target_path = Path("runs/tests/benchmarks/triu").resolve() if target_dir is None else Path(target_dir).resolve()

    assert "runs" in [p.name for p in target_path.parents] or "tmp" in str(target_path) or "pytest" in str(target_path), (
        f"Target directory '{target_path}' must be inside 'runs/' or a temporary directory."
    )

    target_path.mkdir(parents=True, exist_ok=True)
    orig_cwd = Path.cwd()
    os.chdir(target_path)

    try:
        img, mhd_path = _make_tringu_image(target_path)

        # 1. Extract network and set equilateral cross-section
        pnextract(img, {"Overwrite": "true", "OutputName": "tringu"}, verbose=False)
        set_network_equilateral("tringu")

        # 2. Run CNFLOW with debug capillary pressures and stats
        cn_inp = {
            "Overwrite": "true",
            "overwrite": "true",
            "NETWORK": "F tringu",
            "OutputName": "tringuCN",
            "WriteStats": "true",
            "Cycle1": f"0. {1e7 * sigma:.1e} 0.05 T T",
            "Cycle2": f"1. {-1e6 * sigma:.1e} 0.05 T T",
            "InitContAng": "1 0 0 0 0 const 0.0",
            "Water": "0.001 1.0 1000.",
            "Oil": "0.001 1.0 1000.",
            "WaterOil": str(sigma),
            "RandSeed": "1000",
            "forceRun": True,
            "extra_env": {"CNM_DEBUG_PC": "1"},
        }
        ret_cn = cnflow(cn_inp, verbose=False)
        assert ret_cn == 0, f"cnflow failed with exit code {ret_cn}"

        # 3. Run XPM with external network seeding
        xp_inp = {
            "Overwrite": "true",
            "ImageFile": str(mhd_path),
            "OutputName": "tringuXP",
            "NetworkSeed": str(target_path),
            "NetworkPrefix": "tringu",
            "WaterOil": str(sigma),
            "Cycle1": f"0. {1e7 * sigma:.1e} 0.05 T T",
            "Cycle2": f"1. {-1e6 * sigma:.1e} 0.05 T T",
            "extra_env": {"XPM_WRITE_NET_STATS": "1", "XPM_DEBUG_PC": "1"},
        }
        ret_xp = xpm(xp_inp, verbose=False)
        assert ret_xp == 0, f"xpm failed with exit code {ret_xp}"

        # 4. Extract metrics
        cn_svg = (target_path / "tringuCN_upscal.svg").read_text()
        cn_log = (target_path / "tringuCN_cnflow.log").read_text()
        cn_corner_stats = parse_cnm_corner_angle_statistics(cn_log)
        xp_tsv = (target_path / "tringuXP_upscal.tsv").read_text()

        phi_cn = findf(cn_svg, "tringuCN_porosity")
        k_cn = findf(cn_svg, "tringuCN_permeability")
        phi_xp = findf(xp_tsv, "tringuXP_porosity")
        k_xp = findf(xp_tsv, "tringuXP_permeability")

        # Capillary pressures: Primary drainage
        # Middle throat is ID 5 in CNFLOW (index 1 in XPM throat array)
        import numpy as np

        cn_drain, _ = parse_cnm_pc_debug(cn_log)
        pc_entry_mid_cn = cn_drain.get(5, 0.0)
        mean_pc_entry_cn = float(np.mean(list(cn_drain.values()))) if cn_drain else 0.0

        res_dir = target_path / "results"
        xpm_radii_stats = load_xpm_network_statistics(res_dir)
        xp_pri = get_xpm_invasion_entry_pressures(res_dir, cycle="primary", sigma=sigma, pore_count=2)

        pc_entry_mid_xp = float(xp_pri["throat_pc"][1]) if len(xp_pri.get("throat_pc", [])) > 1 else 0.0
        mean_pc_entry_xp = float(xp_pri["throat_pc"].mean()) if len(xp_pri.get("throat_pc", [])) > 0 else 0.0

        # Analytical values for middle throat (R = 6.823568e-7 m)
        r_throat = 6.823568e-7
        pc_entry_ana, _pc_snap_ana = calculate_analytical_equilateral_pc(r_throat, sigma=sigma)

        # Differences
        diff_phi_pct = 100.0 * (phi_xp - phi_cn) / phi_cn if phi_cn else 0.0
        diff_k_pct = 100.0 * (k_xp - k_cn) / k_cn if k_cn else 0.0
        diff_entry_mid_pct = 100.0 * (pc_entry_mid_xp - pc_entry_mid_cn) / pc_entry_mid_cn if pc_entry_mid_cn else 0.0
        diff_entry_avg_pct = 100.0 * (mean_pc_entry_xp - mean_pc_entry_cn) / mean_pc_entry_cn if mean_pc_entry_cn else 0.0

        radii_stats = get_network_radii_statistics(target_path / "tringu")

        # 5. Evaluate imbibition secondary cycle across multiple contact angles (Morrow Model 1)
        ca_results: list[dict[str, Any]] = []
        for th in contact_angles:
            ca_str = f"1 {th} {th} 0 0 const 0.0"
            cn_inp_ca = {
                "Overwrite": "true",
                "overwrite": "true",
                "NETWORK": "F tringu",
                "OutputName": f"tringuCN_{int(th)}",
                "Cycle1": f"0. {1e7 * sigma:.1e} 0.05 T T",
                "Cycle2": f"1. {-1e6 * sigma:.1e} 0.05 T T",
                "InitContAng": "1 0 0 0 0 const 0.0",
                "AlterContAng": ca_str,
                "Water": "0.001 1.0 1000.",
                "Oil": "0.001 1.0 1000.",
                "WaterOil": str(sigma),
                "RandSeed": "1000",
                "forceRun": True,
                "extra_env": {"CNM_DEBUG_PC": "1"},
            }
            cnflow(cn_inp_ca, verbose=False)
            log_th = (target_path / f"tringuCN_{int(th)}_cnflow.log").read_text()
            _, cn_snap_th = parse_cnm_pc_debug(log_th)
            cn_mid_val = cn_snap_th.get(5, 0.0)

            # Clear results directory to isolate each contact angle run
            shutil.rmtree(target_path / "results", ignore_errors=True)
            for f in target_path.glob(f"*{int(th)}*"):
                if f.suffix in (".log", ".tsv", ".json"):
                    f.unlink(missing_ok=True)

            xp_inp_ca = {
                "Overwrite": "true",
                "ImageFile": str(mhd_path),
                "OutputName": f"tringuXP_{int(th)}",
                "NetworkSeed": str(target_path),
                "NetworkPrefix": "tringu",
                "WaterOil": str(sigma),
                "Cycle1": f"0. {1e7 * sigma:.1e} 0.05 T T",
                "Cycle2": f"1. {-1e6 * sigma:.1e} 0.05 T T",
                "InitContAng": "1 0 0 0 0 const 0.0",
                "AlterContAng": ca_str,
                "forceRun": True,
                "extra_env": {"XPM_WRITE_NET_STATS": "1", "XPM_DEBUG_PC": "1"},
            }
            xpm(xp_inp_ca, verbose=False)
            res_dir_th = target_path / "results"
            xp_sec_th = get_xpm_invasion_entry_pressures(res_dir_th, cycle="secondary", sigma=sigma, pore_count=2)
            xp_pri_th = get_xpm_invasion_entry_pressures(res_dir_th, cycle="primary", sigma=sigma, pore_count=2)

            xp_mid_val = float(xp_sec_th["throat_pc"][1]) if len(xp_sec_th.get("throat_pc", [])) > 1 else 0.0
            xp_pri_mid_val = float(xp_pri_th["throat_pc"][1]) if len(xp_pri_th.get("throat_pc", [])) > 1 else 0.0

            # Determine mechanism
            if th >= 60.0 or (xp_mid_val <= 1e-6 and cn_mid_val <= 2e4):
                mech = "Cutoff (None)"
            elif xp_mid_val < xp_pri_mid_val:
                mech = "Snap-off"
            else:
                mech = "Piston"

            diff_mid_pct = 100.0 * (xp_mid_val - cn_mid_val) / cn_mid_val if abs(cn_mid_val) > 1e-3 else 0.0

            cn_avg_val = float(np.mean(list(cn_snap_th.values()))) if cn_snap_th else 0.0
            xp_avg_val = float(xp_sec_th["throat_pc"].mean()) if len(xp_sec_th.get("throat_pc", [])) > 0 else 0.0
            diff_avg_pct = 100.0 * (xp_avg_val - cn_avg_val) / cn_avg_val if abs(cn_avg_val) > 1e-3 else 0.0

            ca_results.append(
                {
                    "theta": th,
                    "mid_mech": mech,
                    "mid_pc_cn": cn_mid_val,
                    "mid_pc_xp": xp_mid_val,
                    "diff_mid_pct": diff_mid_pct,
                    "avg_pc_cn": cn_avg_val,
                    "avg_pc_xp": xp_avg_val,
                    "diff_avg_pct": diff_avg_pct,
                }
            )

        report = {
            "sigma": sigma,
            "radii_stats": radii_stats,
            "xpm_radii_stats": xpm_radii_stats,
            "r_throat": r_throat,
            "phi_cn": phi_cn,
            "phi_xp": phi_xp,
            "diff_phi_pct": diff_phi_pct,
            "k_cn": k_cn,
            "k_xp": k_xp,
            "diff_k_pct": diff_k_pct,
            "pc_entry_ana": pc_entry_ana,
            "pc_entry_mid_cn": pc_entry_mid_cn,
            "pc_entry_mid_xp": pc_entry_mid_xp,
            "diff_entry_mid_pct": diff_entry_mid_pct,
            "mean_pc_entry_cn": mean_pc_entry_cn,
            "mean_pc_entry_xp": mean_pc_entry_xp,
            "diff_entry_avg_pct": diff_entry_avg_pct,
            "ca_results": ca_results,
            "cn_corner_stats": cn_corner_stats,
        }

        if verbose:
            print("\n" + format_radii_comparison_table(radii_stats, xpm_radii_stats, title="TRIU NETWORK: PORE AND THROAT RADII COMPARISON (CNM vs XPM)"))
            if cn_corner_stats:
                print("\n" + format_corner_angle_table(cn_corner_stats, title="TRIU NETWORK: CNM CORNER ANGLE STATISTICS (DEGREES)"))
            print("\n" + "=" * 80)
            print(f"TRIU SYNTHETIC BENCHMARK: CNM vs XPM PETROPHYSICS (sigma = {sigma} N/m)")
            print("=" * 80)
            print(f"{'Metric':<26} {'Analytical':<14} {'CNFLOW':<14} {'XPM':<14} {'Diff CN vs XP':<12}")
            print("-" * 80)
            print(f"{'Porosity phi':<26} {'-':<14} {phi_cn:<14.6f} {phi_xp:<14.6f} {diff_phi_pct:+.3f}%")
            print(f"{'Permeability K (m^2)':<26} {'-':<14} {k_cn:<14.4e} {k_xp:<14.4e} {diff_k_pct:+.2f}%")
            print(f"{'Mid Throat Entry Pc (Pa)':<26} {pc_entry_ana:<14.4e} {pc_entry_mid_cn:<14.4e} {pc_entry_mid_xp:<14.4e} {diff_entry_mid_pct:+.4f}%")
            print(f"{'Mean Throat Entry Pc (Pa)':<26} {'-':<14} {mean_pc_entry_cn:<14.4e} {mean_pc_entry_xp:<14.4e} {diff_entry_avg_pct:+.4f}%")
            print("=" * 80 + "\n")
            print(format_multi_ca_table(ca_results, title=f"TRIU: IMBIBITION SECONDARY CYCLE: MIDDLE THROAT PRESSURES (sigma = {sigma} N/m)"))
            print()

        return report
    finally:
        os.chdir(orig_cwd)


if __name__ == "__main__":
    benchmark_dir = Path("runs/tests/benchmarks/triu").resolve()
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    _make_tringu_image(benchmark_dir)
    print(f"Executing triu synthetic benchmark in {benchmark_dir}...")
    run_triu_benchmark(target_dir=benchmark_dir, sigma=1.0, verbose=True)
