"""pore-scale models and parameters, Contents: Seri, Prop, Method, VoxImg and FlowSom  classes"""

from __future__ import annotations

import argparse
import colorsys
import copy
from pathlib import Path
from typing import Any, Callable

import matplotlib.markers as mmarkers
import matplotlib.path as mpath
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
import numpy as np

from .process import (
    get_oil_r,
    get_scalar,
    get_si_sr,
    get_sor,
    get_table,
    grep_swi,
    run_cp_dns1f,
    run_par,
    run_ske,
    run_skip,
    run_xnflow,
)
from .runtime import dbg_msg, disp, ensure
from .xpm import run_xpm

parser = argparse.ArgumentParser(conflict_handler="resolve")


def _str_to_bool(s):
    """Convert string to bool (in argparse context)."""
    assert s.lower() in ["true", "false", "0", "1"], f"Need bool; got {s}"
    return {"true": True, "false": False, "1": True, "0": False}[s.lower()]


def bool_arg(name, default=False):
    """Add a boolean argument to an ArgumentParser instance."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(f"--{name}", nargs="?", default=default, const=True, type=_str_to_bool)
    group.add_argument(f"--no{name}", dest=name, action="store_false")


def bool_args(names, default=False):
    for nam in names:
        bool_arg(nam, default)


def str_arg(name, default=""):
    parser.add_argument(f"--{name}", default=default)


def parse_args(markdown="", *args_in, **kwargs):
    str_arg("sens")  # sensitivity params
    str_arg("rTg")  # rename (retag) prop
    str_arg("mhds")  # mhd/image names
    str_arg("markdown", default=markdown)
    bool_args(("DNS", "SKE", "snsi", "si"))  # run DNS, SKElor or flow seni(tivity)
    args = parser.parse_args()
    args.sens = args.sens.split(",") if args.sens else []
    return args


numenclature = {}


def to_caption(nam):
    for di, dv in numenclature.items():
        nam = nam.replace(di, dv)
    return nam


#################################### Plot helpers ####################################

fontsiz = 14
scalImg = 1.5
plt.rcParams.update({"font.family": "serif", "font.size": fontsiz})
plt.rc("legend", fontsize=fontsiz)

PatchDEA = False


class Seri:  # a plot line/series style (sty)
    markr: str | mmarkers.MarkerStyle | mpath.Path = ""
    clrW = "#ff0000"

    def __init__(self, markr="+", clr="#bbbbbb", mw=1.0, ms=5.0, ls="-", lw=2.0, dsh=None, al=0.9):
        self.markr = markr  # marker
        self.clrW = clr  # colour
        self.mw = mw  # marker width
        self.ms = ms  # marker size
        self.ls = ls  # line style
        self.lw = lw  # line width
        self.mclr = clr  # marker colour
        self.dsh = dsh  # dash
        self.al = al  # alpha


def seriof(redness, ls="-"):
    """scalar to series conversion"""
    rgb = colorsys.hsv_to_rgb(0.63 - redness * 0.62, 0.9, 255)  # h=0.6666666 is blue # h=0. is red
    factor = (max(rgb) * 3) / (sum(rgb) + 2 * max(rgb))
    rgb = tuple([factor * x for x in rgb])
    hx1 = f"#{int(rgb[0]):02x}{int(rgb[1]):02x}{int(rgb[2]):02x}"
    wst = Seri("", clr=hx1, mw=1, ms=3, ls=ls, lw=2)
    wst.markr = (
        mmarkers.MarkerStyle("^").get_path().transformed(mtransforms.Affine2D().scale(0.6, 1.0).rotate_deg(redness * 180 - 90))
    )  # python ><^ are aggly and wrong
    return wst


try:  #'plot series styles'
    #     marker    colour maerke-width,size line-style  line-width
    sSN = Seri("+", "#1b6fdf", mw=1, ms=5, ls="-", lw=2)  # SNM
    sXN = Seri("$*$", "#00bfbf", mw=1, ms=5, ls="--", lw=2, dsh=[6, 3])  # XPM
    sPN = Seri("x", "#c72e3a", mw=1, ms=5, ls="-.", lw=2, dsh=[6, 2, 2, 2])
    sEX = Seri("x", "#000000", mw=3, ms=10, ls="None", lw=0)  # experiment
    sE1 = Seri("o", "#5500bb", mw=1, ms=5, ls="-", lw=2)
    sE2 = Seri("s", "#00ff55", mw=1, ms=5, ls="-", lw=2)
    sE3 = Seri("v", "#bb00ff", mw=1, ms=5, ls="-", lw=2)
    sE4 = Seri("^", "#ff99bb", mw=1, ms=5, ls="-", lw=2)
    sE5 = Seri("d", "#b5a12b", mw=1, ms=5, ls="-", lw=2)
    sE6 = Seri("D", "#e2b03d", mw=1, ms=5, ls="-", lw=2)
    sE7 = Seri("<", "#784f3c", mw=1, ms=5, ls="-", lw=2)
    sE8 = Seri(">", "#af70da", mw=1, ms=5, ls="-", lw=2)
    sAn = Seri("D", "#11e1e1", mw=1, ms=5, ls="--", lw=2, dsh=[6, 2])  # Analytical
    sCN = Seri("x", "#bb4570", mw=1, ms=5, ls="-.", lw=3, dsh=[6, 3])  # Classical net
    sM_ = Seri("x", "#bbbbbb", mw=0, ms=0, ls="-", lw=2.5, al=0.5)  # Drainage cycle

    seris = [
        sXN,
        sSN,
        sPN,
        sE1,
        sE2,
        sE3,
        sE4,
        sE5,
        sE6,
        sE7,
        sE8,
        sPN,
        sE1,
        sE2,
        sE3,
        sE4,
        sE5,
        sE6,
        sE7,
        sE8,
        sPN,
        sE1,
        sE2,
        sE3,
        sE4,
        sE5,
        sE6,
        sE7,
        sE8,
    ]

    sriGrad = [
        sXN,
        sSN,
        sE1,
        sE2,
        sE3,
        sE4,
        sE5,
        sE6,
        sE7,
        sE8,
        sPN,
        sXN,
        sE1,
        sE2,
        sE3,
        sE4,
        sE5,
        sE6,
        sE7,
        sE8,
        sPN,
        sXN,
        sE1,
        sE2,
        sE3,
        sE4,
        sE5,
        sE6,
        sE7,
        sE8,
        sPN,
    ]

    serisL = copy.deepcopy(sriGrad)
    for sri in serisL:
        sri.ls = "-"
        sri.ms = 1
        sri.lw = 2
        sri.mw = 0.5
except:
    raise


def get_color_gradxy(alpha=None, linst=None, dshs=None, linwt=None, ms=1, mw=0.5):
    if linwt is None:
        linwt = [1.5, 1.0, 1.5]
    if dshs is None:
        dshs = [[3, 1], [], [3, 1, 1, 1]]
    if alpha is None:
        alpha = [0.8, 1.0, 0.8]
    linst = ["--", "-", "-."] if linst is None else linst
    sriGradxy = [
        copy.deepcopy(sriGrad),
        copy.deepcopy(sriGrad),
        copy.deepcopy(sriGrad),
    ]
    for jj, sriG in enumerate(sriGradxy):
        for sri in sriG:
            sri.ls = linst[jj]
            sri.lw = linwt[jj]
            sri.dsh = dshs[jj]
            sri.ms = ms
            sri.mw = mw
    return sriGradxy


def get_ca_sw_colors_hsv(nCA=5, nSw=3, dshs=None):
    """The inner loop has gradient in thickness and alpha, for Swi, outer has gradient in color range, for CA"""
    if dshs is None:
        dshs = [(1, 0), (1, 1), (5, 2), (1, 2), (5, 5)]
    sriGradxy = []
    for jj in range(nCA):
        sriGradxy.append([])
        for ii in range(nSw):
            sr = seriof(jj / (nCA - 1 + 0.01))
            sr.dsh = dshs[ii % len(dshs)]
            sriGradxy[jj].append(sr)
    return sriGradxy


class _PloT:  # plot functor wrpping plt.plot, with optional uncertainty  handling for UncSim class
    errbar = False

    def __init__(self, pplot=plt.plot):
        self.pplot = pplot

    def __call__(self, datax, datay, prp, sty: Seri, sim=None, icy=0, icol=0):
        # return self.pplot(datax,datay, color=sty.clrW,linestyle=sty.ls,linewidth=sty.lw, marker=sty.markr,markeredgewidth=sty.mw, markeredgecolor=sty.mclr,ms=sty.ms, alpha=sty.al,dashes=sty.dsh)
        if isinstance(sim, (UncSim,)) and len(sim.sims) >= 3:  # add uncertainty range
            if self.errbar:
                xrf_ = sim.getRes_(prp, icy, varI="bgn")
                xy1_ = sim.getRes_(prp, icy, varI="2nd")
                xy2_ = sim.getRes_(prp, icy, varI="end")
                if isinstance(xrf_, np.ndarray) and isinstance(xy1_, np.ndarray) and isinstance(xy2_, np.ndarray):
                    xy1 = xy1_[~np.isnan(xy1_)[:, icol]]
                    xy2 = xy2_[~np.isnan(xy2_)[:, icol]]
                    xrf = xrf_[~np.isnan(xy1_)[:, icol]][:, prp.xcol]
                    yrf = xrf_[~np.isnan(xy1_)[:, icol]][:, icol]
                    eux = xrf - xy1[:, prp.xcol]
                    euy = (yrf - xy1[:, icol]) / prp.unit
                    xrf = xrf_[~np.isnan(xy2_)[:, icol]][:, prp.xcol]
                    yrf = xrf_[~np.isnan(xy2_)[:, icol]][:, icol]
                    elx = xy2[:, prp.xcol] - xrf
                    ely = (xy2[:, icol] - yrf) / prp.unit

                    plt.errorbar(xrf, yrf / prp.unit, yerr=[euy, ely], xerr=[eux, elx], color=sty.clrW, marker=None, alpha=sty.al)
                else:
                    print("Error: wrong data types")
            varIs = ["2nd", "bgn", "end"]
            for pm in (1, 2):
                xy1 = sim.getRes_(prp, icy, varI=varIs[pm - 1])
                xy2 = sim.getRes_(prp, icy, varI=varIs[pm - 0])
                if isinstance(xy1, np.ndarray) and isinstance(xy2, np.ndarray):
                    xy1 = xy1[~np.isnan(xy1)[:, icol]]
                    xy2 = xy2[~np.isnan(xy2)[:, icol]]
                    xf = np.concatenate((xy1[:, prp.xcol], xy2[::-1, prp.xcol]))
                    yf = np.concatenate((xy1[:, icol], xy2[::-1, icol]))
                    if self.pplot == plt.semilogy:
                        yf = np.array([max(yi, prp.small) for yi in yf])
                    plt.fill(xf, yf / prp.unit, sty.clrW + sim.alpha)
            if self.pplot in (plt.semilogx, plt.loglog):
                plt.xscale("log", nonpositive="clip")
            if self.pplot in (plt.semilogy, plt.loglog):
                plt.yscale("log", nonpositive="clip")
        if self.pplot == plt.semilogy:
            datay = np.array([max(yi, prp.small) for yi in datay])
        dsh_kw = {"dashes": sty.dsh} if sty.dsh is not None else {}
        return self.pplot(
            datax,
            datay / prp.unit,
            color=sty.clrW,
            linestyle=sty.ls,
            linewidth=sty.lw,
            marker=sty.markr,
            markeredgewidth=sty.mw,
            markeredgecolor=sty.mclr,
            ms=sty.ms,
            alpha=sty.al,
            **dsh_kw,
        )


#################################### Pore-scale methods ####################################

AllMtds = {}


class Method:  # this stands for simulation/.. method
    def __init__(self, name, styl, cmdapp="", outsfx="", netsfx="", runSim=run_xnflow, res_prefix=None, args=None):
        self.setName(name)
        self.mtdstyl = styl
        self.app = cmdapp
        self.outsfx = outsfx
        self.netsfx = netsfx  # without .xmf, these are used in runSim=run_xnflow
        self.runSim = runSim  # called from FlowSim.runSim()
        if res_prefix is not None:
            self.res_prefix = res_prefix
        self.args = {} if args is None else args  # simulation and arguments

    def setName(self, name):
        self.mNam = name  # use in serious stuff!
        self.name = name  # use in IO/logging!
        AllMtds[name] = self
        self.res_prefix = f"results{name}/"  # resultsSNM/ etc

    def simArgs(self):
        return {"app": self.app, "resDir": self.res_prefix, **self.args}

    def copy(self, name):
        cp = copy.deepcopy(self)
        cp.setName(name)
        return cp


# Flow models
mEx = Method("Exp", sE1, cmdapp="", outsfx=".tsv", res_prefix="Exp/", runSim=run_skip)
mDS = Method("DNS", sAn, cmdapp="", outsfx="_relPerms.tsv", res_prefix="DNS/", runSim=run_cp_dns1f)
mCN = Method("CNM", sCN, cmdapp="cnflow", outsfx="_upscal.tsv", netsfx="Net")
mSN = Method("SNM", sSN, cmdapp="scalor", outsfx="_upscal.svg")
mPN = Method("PNM", sCN, cmdapp="pnflow", outsfx="_upscal.tsv", netsfx="Net")
mXP = Method("XPM", sXN, cmdapp="xpm", outsfx="_upscal.tsv", runSim=run_xpm)
mDy = Method("DSY", sAn, cmdapp="", outsfx="_relPermsY.tsv", res_prefix="DNS/", runSim=run_cp_dns1f, args={"axs": "Y"})
mDz = Method("DSZ", sAn, cmdapp="", outsfx="_relPermsZ.tsv", res_prefix="DNS/", runSim=run_cp_dns1f, args={"axs": "Z"})
mAn = Method("Anl", sAn, cmdapp="")

# pre-processing /network extraction
mSK = Method("SKE", sSN, cmdapp="skelor", res_prefix="SKE/", runSim=run_ske)
mNE = Method("PNE", sSN, cmdapp="pnextract", res_prefix="PNE/", runSim=run_ske)


""" ============= class VoxImg ============== """

class VoxImg:
    def __init__(self, name, netDir="../../SKE"):
        self.name = str(name)
        self.expImg = str(name)
        self.netDir = str(netDir)  #  =imgDir or networks dir

    def netname(self, mtd):
        # dbg_msg(f"vxl Img, for mtd: {mtd.mNam},  netname: {self.name}{mtd.netsfx}", 2)
        return self.name + mtd.netsfx


mhds = []  # set this manually to avoid looking for .mhd files


def get_pwd_images(hdrs=None):
    hdrs = hdrs if hdrs else mhds
    imgs = []
    try:
        if hdrs and len(hdrs) > 0:
            imgs = [VoxImg(f[0:-4] if f[-4] == "." else f) for f in hdrs]
        else:
            imgs = [
                VoxImg(p.name[0:-4])
                for p in sorted(Path().iterdir())
                if len(p.name) > 4 and p.name[-4:] == ".mhd" and Path(f"{p.name[0:-4]}/{p.name}").is_file()
            ]
            for img in imgs:
                img.netDir = f"../{img.name}"  # used when running AllRunImageNEPar
        disp(f"Images:  {[f.name for f in imgs]!s}, dir: {Path.cwd()}")
    except OSError as e:
        dbg_msg(f"No images found in {Path.cwd()}")
        disp(e)
    return imgs


""" ============= Prop(ertie)s ============== """

AllPrps = {}


class Prop:
    valBfor = ""  # input keyword before values
    valAftr = ""  # input keyword post values
    nSkip = 0  # nSkipLines/words before val, used in getRes...

    def __init__(self, name, lbl, dscr, Dy=None, kywrd="", endKy=";", valpre="", valpost=""):
        if Dy is None:
            Dy = [0.0, 1.0]
        self.name: str = name  # instance variable unique to each instance
        self.lbl: str = lbl
        self.dscr: str = dscr
        self.xlbl: str = "$S_w$"
        self.grab_fn: Callable[..., Any] = get_table  # ideally shall be called through FlowSim.getRes
        self.xcol: int = 0
        self.icol: int = 0
        self.icol2: int = 0  # icol=0 indicate scalarness (not array)
        self.unit: float = 1.0
        self.small: float = 1e-15
        self.Dx = [0.0, 1.0]
        self.Dy: list[float] | None = Dy
        self.setXAxis = Prop.xAtBorder  # set ylim xlim range
        self.kywrd: str = kywrd if kywrd else name
        self.endKy: str = endKy
        self.filExt: str = ""
        self.icycle: int = 0  # mutable
        self.setFunc: Callable[..., Any] | None = None
        self._ploT = _PloT(plt.plot)
        AllPrps[name] = self

    def ploT(self, datax, datay, sty: Seri, sim=None, icy=0, icol=0):
        return self._ploT(datax, datay, prp=self, sty=sty, sim=sim, icy=icy, icol=icol)

    def setLogy(self, Dy=None):
        self._ploT.pplot = plt.semilogy
        self.Dy = Dy if Dy is not None else [0.001, 1.0]
        self.setXAxis = Prop.xAtBorder

    def setLogLog(self, Dy=None):
        self._ploT.pplot = plt.loglog
        self.Dy = Dy if Dy is not None else [0.001, 1.0]
        self.setXAxis = Prop.xAtBorder

    def setLinear(self, Dy=None):
        self._ploT.pplot = plt.plot
        self.Dy = Dy if Dy is not None else [0.0, 1.0]

    def __str__(self):
        return self.name + (f"-cycle{self.icycle!s}" if self.icycle else "")  # +' ky:'+self.kywrd

    def isArray(self):
        return self.icol

    def xAtYzero(self, ax):
        ax.spines["bottom"].set_alpha(0.8)
        ax.spines["left"].set_alpha(0.8)
        ax.spines["top"].set_color("none")
        ax.spines["right"].set_color("none")
        ax.set_alpha(0.8)
        ax.spines["bottom"].set_position(("data", 0))
        if self.Dy and self.Dy[0] < self.Dy[1]:
            plt.ylim(self.Dy[0], self.Dy[1])
        if self.Dx[0] < self.Dx[1]:
            plt.xlim(self.Dx[0], self.Dx[1])

    def xAtBorder(self, ax):
        ax.spines["bottom"].set_alpha(0.8)
        ax.spines["top"].set_alpha(0.8)
        ax.spines["right"].set_alpha(0.8)
        ax.spines["left"].set_alpha(0.8)
        ax.set_alpha(0.8)
        if self.Dy and self.Dy[0] < self.Dy[1]:
            plt.ylim(self.Dy[0], self.Dy[1])
        if self.Dx[0] < self.Dx[1]:
            plt.xlim(self.Dx[0], self.Dx[1])

    def __hash__(self):
        return hash(self.name)  # for using prop as dict key

    def __eq__(self, other):
        return self.name == other.name

    def __ne__(self, other):
        return not (self == other)

    def toTag(self, val):
        if isinstance(val, (list, np.ndarray)):
            return self.name + "".join(map(str, val))
        return self.name + str(val)


try:  #'Props' # to make it a class named `Proptis``
    pNon = Prop("", "Property", "Description")
    plPc = Prop("Pc", r"$P_c/\sigma$ $(10^5/m)$", "curvature (10^5/m)", [-10.0, 20.0])
    plPc.icol = 1
    plPc.unit = 0.03 * 100000
    plPc.setXAxis = Prop.xAtYzero
    plKr = Prop("Kr", r"$k_r$", "relative permeability", [0.0, 1.0])
    plKr.icol = 2
    plKr.icol2 = 3
    plKw = Prop("Krw", r"$k_{rw}$", "water Kr", [0.0, 1.0])
    plKw.icol = 2
    plKo = Prop("Kro", r"$k_{ro}$", "oil Kr", [0.0, 1.0])
    plKo.icol = 3
    plRI = Prop("RI", r"$RI$", "resistivity index", [1.0, 1000.0])
    plRI.icol = 4
    plRI.Dx = [0.01, 1.0]
    plRI.small = 1.0
    plRI.setLogLog()
    OilR = Prop("OilR", "Oil Recovery, FOIP", "oil recovery factor", [0.0, 1.0])
    OilR.grab_fn = get_oil_r
    OilR.icycle = 2
    pSgr = Prop("Sgr", r"$S_{gr}$", "gas residual saturation", [0.0, 0.7])
    pSgr.grab_fn = get_si_sr
    pSgr.icycle = 2
    pSgr.xlbl = r"$S_{gi}$"
    pSor = Prop("Sor", r"$S_{or}$", "oil residual saturation", [0.0, 0.7])
    pSor.grab_fn = get_sor
    pSor.icycle = 2
    pPhi = Prop("porosity", r"$\phi$", "porosity")
    pPhi.grab_fn = get_scalar
    pKsp = Prop("permeability", r"$k_{abs}$", r"permeability \(D\)", [0.0, 1e-6])
    pKsp.grab_fn = get_scalar
    pKsp.unit = 9.869233e-13
    pFF = Prop("formationfactor", r"$FF$", "formation factor", [0.0, 1000.0])
    pFF.grab_fn = get_scalar
    pFF.Dx = [0.01, 1.0]
    pFF.small = 1.0
    pSwD = Prop("Swi", r"$S_{wi}$", "initial water saturation", [0.0, 1.0])
    pSwD.grab_fn = grep_swi
    pSwD.icycle = 1
    Amot = Prop("Amot", "Amott index", "Ammot index", [-1.0, 1.0], "AmottI")
    Amot.grab_fn = get_scalar
    pnTg = Prop("pnTg", "Network tag", "Network")  # efect of voxel size ...

    Clay = Prop("Clay", "$S_w$ sub-res.", "sub-resolution porosity", [0, 1], "AddClay")
    CAdv = Prop("CAdv", "$θ_{adv}$", "advancing contact$~$angle", [0, 180], "AlterContAng")
    CAdv.valBfor = "4 "
    CAdv.valAftr = " 0.2 -3.  rand   0."
    CBox = Prop("CBox", "$k_r$ Calc Box", "upscaling bounds", [0.0, 1.0], "UpscaleBox")
    NpIm = Prop("NpIm", "Pressure drop", "pressure difference", [0.0, 1.0], "Cycle2_BC")
    NpIm.valBfor = "T   F       T   T      DP   "
    pSwi = Prop("Swi", "$S_{wi}$", "initial water saturation", [0.0, 1.0], "Cycle1")
    pSwi.valAftr = "  1e5   0.025     T   T"
    pPci = Prop("Pci", "$P_{ci}$", "initial capillary pressure", [0.0, 1e5], "Cycle1")
    pPci.valBfor = "0. "
    pPci.valAftr = "   0.05     T   T"

    for prp in [plPc, plKr, plKw, plKo, plRI, OilR, pSgr, pSor, pSwD]:
        prp.kywrd = "_SwPcKrwKroRI_cycle"
        prp.nSkip = 2
        prp.endKy = "\n\n"

    DelPw = Prop("DelPw", r"${\Delta}P_w$", "Water viscous pressure difference", [0, 1000], "Cycle2_BC")
    DelPw.valBfor = "T F  T T  DP "
    DelPw.valAftr = " 1"
    DelPo = Prop("DelPo", r"${\Delta}P_o$", "Oil viscous pressure difference", [0, 1000], "Cycle2_BC")
    DelPo.valBfor = "T F  T T  DP  1 "

    CArc = Prop("CArc", r"$θ_{rec}$", "receding contact$~$angle", [0, 180], "InitContAng")
    CArc.valBfor = "1 "
    CArc.valAftr = " 0.2 -3.   rand   0."
    CAdv = Prop("CAdv", r"$θ_{adv}$", "advancing contact$~$angle", [0, 180], "AlterContAng")
    CAdv.valBfor = "4 "
    CAdv.valAftr = " 0.2 -3.  rand   0."
    Clay = Prop("Clay", r"$S_w$ sub-res.", "sub-resolution porosity", [0, 1], "AddClay")

    AAow = Prop("AAow", "$θ_{frac}$", "fractionally altered contact$~$angle", [0, 180], "FracContAng")
    AAow.valBfor = "4 "
    AAow.valAftr = " 0.2 -3.   rand   0."
    AAal = Prop("AAal", "$θ_{all}$", "Advancing contact$~$angles", [0, 180], "FracContAng")
    AAal.valBfor = "4 "
    AAal.valAftr = " 0.2 -3.   rand   0."  # same as AAow but use for spatially correlated single-wettability distribution
    AAfr = Prop("AAfr", "Altered-wet fraction", "altered contact$~$angle fraction", [0, 180], "FracContOpt")
    AAfr.valAftr = " V   O  corr O    1   3   0.2 -3.    rand"
    AAxC = Prop("AAxC", "$θ_{frac}$ cor.len.", "wettability spatial correlation", [0, 180], "FracContOpt")
    AAxC.valBfor = "0.7 V   O  corr O  "
    AAxC.valAftr = "  0.2 -3.    rand"

    FOrC = Prop("FOrC", "$θ_{frac}$ R.cor.", "fractional-wettability radius correlation", [0, 180], "FracContOpt")
    FOrC.valBfor = "0.7  V   O  corr O    1   3   0.2 -3. "
    CArC = Prop("CArC", "$θ_{adv}$ R.cor.", "contact$~$angle radius correlation", [0, 180], "AlterContAng")
    CArC.valBfor = "-1 TOSET 4  CAmin CAmax 0.2 -3."
    CArC.valAftr = "  0."
    FRrC = Prop("FRrC", "$θ_{adv}$ R.cor.", "contact$~$angle radius correlation", [0, 180], "FracContAng")
    FRrC.valBfor = "-1 TOSET 4  CAmin CAmax 0.2 -3."
    FRrC.valAftr = "  0."

    def setAllRMaxMinRand(sim, prp, val):  # noqa: ARG001 (prp kept for Prop.setFunc interface)
        sim.setInpTag(FOrC, val)
        sim.setInpTag(CArC, val)
        sim.setInpTag(FRrC, val)

    FArC = Prop("FArC", "$θ_{adv}$ R.cor.", "contact$~$angle radius correlation", [0, 180])
    FArC.setFunc = setAllRMaxMinRand

    slvTyp = Prop("slvTyp", "solver type", "solver type", [0, 5], "Solver")
    slvTyp.valAftr = " 1e-18 1e-29  1000  F  F  1e18"
    slvTol = Prop("slvTol", "solver tolerance", "solver tolerance", [0, 1], "Solver")
    slvTol.valBfor = "1 "
    slvTol.valAftr = " 1e-29  1000  F  F  1e18"
    slvCut = Prop("slvCut", "cond. cut-off", "solver cond. cut-off", [0, 1], "Solver")
    slvCut.valBfor = "1  1e-18 "
    slvCut.valAftr = "  1000  F  F  1e18"
    slvCap = Prop("slvCap", "cond. cap factor", "solver cond. cap factor", [0, 1], "Solver")
    slvCap.valBfor = "1  1e-18 1e-29 "
    slvCap.valAftr = "   F  F  1e18"
    slvScl = Prop("slvScl", "solver scale", "solver scale factor", [0, 1], "Solver")
    slvScl.valBfor = "1  1e-18 1e-29  1000  F  F "
except:
    raise


""" ============= FlowSim ============== """


class FlowSim:  # Flow simulation data (Method, image, parameters .series style)
    def __init__(self, tag: str, lgnd: str, img: VoxImg, mtd: Method, styl: Seri, keyVals: dict, force_rerun=False):  # FlowSim()
        self.tag = tag  # simulation output suffix
        self.lgnd = to_caption(lgnd)  # simulation plots legend,
        self.img = img
        self.mtd = mtd
        self.force_rerun = force_rerun
        self.styl = styl
        self.keyVals = keyVals.copy()
        self.resStrs_ = {}  # catch output files
        self.logs_ = ""
        self.simres = {}

    def runSim(self, nam, forceRun=None):
        if forceRun is None:
            forceRun = self.force_rerun

        img = self.img
        mtd = self.mtd
        disp(f"\n\n{nam}, FlowSim.{mtd.name}.{mtd.runSim.__name__} from {Path.cwd()}, {self.tag}")  # : {self.keyVals}
        ret = mtd.runSim(kwrds=self.keyVals, netnam=img.netname(mtd), resSuffix=self.tag, forceRun=forceRun, netDir=img.netDir, **mtd.simArgs())
        ensure(ret == 0, f"Failed: {mtd.name}.{mtd.runSim.__name__} on {img.name}, see {self.logPath()}")
        return ret

    def setInpTag(self, prp: Prop, val):
        if prp.setFunc:
            tag = self.tag
            prp.setFunc(self, prp, val)
            if PatchDEA:
                self.tag = tag + prp.name + str(val)
        elif isinstance(val, (list, np.ndarray)):  # ,pd.core.series.Series
            self.keyVals[prp.kywrd] = f"{prp.valBfor} {' '.join(map(str, val))} {prp.valAftr}"
            self.simres[prp.name] = val
            self.tag += prp.name + "".join(map(str, val))
        else:
            self.keyVals[prp.kywrd] = f"{prp.valBfor} {val!s} {prp.valAftr}"
            self.simres[prp.name] = val
            self.tag += prp.name + str(val)

    def getRes_(self, prp: Prop, icycl=0):  # , pTg=''
        # ky=prp.name+pTg+(str(icycl) if icycl else '')
        ky = prp.name + (str(icycl) if icycl else "")
        if ky in self.simres:
            return self.simres[ky]
        if icycl:
            prp.icycle = icycl
        res = prp.grab_fn(self, prp)
        if np.isscalar(res) and prp.Dy is not None and isinstance(res, float):
            if res < prp.Dy[0]:
                disp(f"outside bounds, {ky}: {res!s}")
                res = max(res, prp.Dy[0] - 0.1 * (prp.Dy[1] - prp.Dy[0]))
            if res > prp.Dy[1]:
                disp(f"outside bounds, {ky}: {res!s}")
                res = min(res, prp.Dy[1] + 0.1 * (prp.Dy[1] - prp.Dy[0]))
        self.simres[ky] = res
        return res

    def getRes(self, prp: Prop, icycl=0):
        ret = self.getRes_(prp, icycl)
        if abs(prp.unit - 1) > 0.01 and prp.unit > 1e-11 and (isinstance(ret, (float, np.ndarray))):
            disp(f"{prp.name}.unit: {prp.unit}")
            return ret / prp.unit
        return ret

    def resName(self):
        return self.img.netname(self.mtd) + self.tag

    def resPath(self, prp: Prop = pNon) -> Path:
        return Path(self.mtd.res_prefix + self.resName() + prp.filExt + self.mtd.outsfx).absolute()

    def resFile(self, prp: Prop = pNon) -> str:
        return str(Path(self.mtd.res_prefix + self.resName() + prp.filExt + self.mtd.outsfx).absolute())

    def logPath(self) -> Path:
        return Path(f"{self.mtd.res_prefix}{self.resName()}_{self.mtd.app}.log").absolute()

    def getLines(self, prp: Prop) -> str:
        """read and catch output files"""
        nam = f"_{prp.filExt}"  # = self.resFile(prp)
        if nam not in self.resStrs_:
            with self.resPath(prp).open() as f:
                self.resStrs_[nam] = f.read()
        return self.resStrs_[nam]

    def getLogs(self) -> str:
        if not self.logs_:
            with self.logPath().open() as f:
                self.logs_ = f.read()
        return self.logs_


""" ============= Uncertainty ============= """


def mapxys(xy, xref):
    """map xy tabulation to scaled xref, scaled by xy[:,0]s range,
    leading to one-to-one correspondence in the data points"""
    minx1, minx2 = min(xref), min(xy[:, 0])
    newx = (xref - minx1) * (max(xy[:, 0]) - minx2) / (max(xref) - minx1) + minx2
    res = [newx]
    for ii in range(1, len(xy[0])):
        res.append(np.interp(newx, xy[:, 0], xy[:, ii]))
    return np.transpose(np.array(res))


_pI = 0  # _pI  to switch start index, between 0 or 1


class UncSim:  # Uncertainity quantification using a set of FlowSim, by default tagged by I0,I1...
    nProc = 8
    nSim = 8
    _I_ = "I"  # default   ***UncSim.nProc***, ***UncSim.nSim*** and ***UncSim._I_***
    alpha = "80"

    def __init__(self, tag, nSim=8, sims: list[FlowSim] | None = None, tags: list[str] | None = None, **kwargs):  # agns0 shall be tag
        if sims is not None:
            self.sims = sims
        elif tags is not None:
            print("UncSim", tag, tags)
            self.sims = [FlowSim(tag + tg, **kwargs) for tg in tags]
        else:
            self.sims = [FlowSim(UncSim._I_ + str(ii + _pI) + tag, **kwargs) for ii in range(nSim)]
        self.tag = tag
        self.img = self.sims[0].img
        self.mtd = self.sims[0].mtd  # used in disp
        self.styl = self.sims[0].styl
        self.lgnd = self.sims[0].lgnd
        self.simres = {}

    def runSim(self):
        run_par(self.sims, self.nProc)

    def resName(self):
        return f"Unc-{self.img.name}{self.tag}"

    def resPath(self, prp=pNon):  # noqa: ARG002 (prp kept for interface parity with FlowSim.resPath)
        raise RuntimeError("Unc Sim:res Path")  # noqa: EM101

    def logPath(self):
        raise RuntimeError("Unc Sim:log Path")  # noqa: EM101

    def setInpTag(self, prp, val):
        for sim in self.sims:
            sim.setInpTag(prp, val)

    def getRes_(self, prp, icycl=0, varI=""):
        ky = f"{prp.name}{str(icycl) if icycl else ''}_{varI}"
        if ky in self.simres:
            return self.simres[ky]

        ress = []
        for sim in self.sims:
            ress.append(sim.getRes_(prp, icycl))
        res = ress[0]  # by default return first value
        if varI and isinstance(res, (list, np.ndarray)):  # ,pd.core.series.Series # if kr, pc, RI
            # for rs in ress[1:]:   rs = mapxys(rs, res[:,0]) # resize and map after scaling x
            if varI == "bgn":
                res = ress[0]
            elif varI == "2nd":
                res = ress[1]
            elif varI == "end":
                res = ress[-1]
            # if   varI=='high':
            # for ii in range(len(ress[0])):   res[ii] = st.max(ress[:][ii])
            # elif varI=='low':
            # for ii in range(len(ress[0])):   res[ii] = st.min(ress[:][ii])
            # elif varI=='sdv': # standard deviation
            # for ii in range(len(ress[0])):   res[ii] = st.pstdev(ress[:][ii])
            # elif varI=='avg': # standard deviation
            # for ii in range(len(ress[0])):   res[ii] = st.mean(ress[:][ii])
            elif varI == "sdv":  # standard deviation
                resz = np.array(ress)
                res = np.std(resz)  # ; ensure(len(mean)==len(ress[0]))

            else:
                dbg_msg("bad varI")
                # for ii in range(len(ress[0])):   res[ii] = st.mean(ress[:][ii])
        elif varI:
            if varI == "max":
                res = max(ress)
            elif varI == "sdv":
                res = np.std(ress)  # .pstdev(ress)
            else:
                res = np.mean(ress)
        self.simres[ky] = res
        return res

    def getRes(self, prp, icycl=0, varI=""):
        return self.getRes_(prp, icycl, varI) / prp.unit

    def getLines(self, prp):  # noqa: ARG002 (prp kept for interface parity with FlowSim.getLines)
        raise RuntimeError("Unc Sim:getLines")  # noqa: EM101

    def getLogs(self):
        raise RuntimeError("Unc Sim:getLogs")  # noqa: EM101


class UncNetSim(UncSim):
    def __init__(self, tag, *args, **kwargs):
        UncSim.__init__(self, tag, *args, **kwargs)
        for ii, sim in enumerate(self.sims):
            sim.mtd = copy.deepcopy(sim.mtd)
            sim.mtd.netsfx = f"I{ii!s}{sim.mtd.netsfx}"  # prepend tag to mtd.netsfx


class Unc3Sim(UncSim):  # Uncertainity using a set of 3 FlowSim s: mean/mid, min and max
    def __init__(self, tag, *args, **kwargs):
        UncSim.__init__(self, tag, *args, nSim=3, **kwargs)
