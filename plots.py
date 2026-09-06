"Run and plot functions for running sensitivity studies ..."

from __future__ import annotations

import copy
import os
import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import curve_fit

from . import models
from .models import (
    Amot,
    CAdv,
    FlowSim,
    OilR,
    UncSim,
    fontsiz,
    get_ca_sw_colors_hsv,
    get_pwd_images,
    mCN,
    mDS,
    mEx,
    mSN,
    mXP,
    pFF,
    pKsp,
    plKr,
    plPc,
    plRI,
    pNon,
    pPhi,
    pSgr,
    pSwi,
    scalImg,
    sCN,
    sE2,
    sE7,
    sE8,
    seris,
    sEX,
    sM_,
    sriGrad,
    sSN,
    sXN,
    to_caption,
)
from .process import nil_fn, run_par
from .runtime import alert, dbg_msg, disp, ensure, mkdr

plIcycls = [1, 2]
autoInitCA = "1   0   10  -0.2    -3.   rand   0."
plPcKrRI = [plPc, plKr, plRI]
nPyProc = len(os.sched_getaffinity(0))
_SimTyp = FlowSim


def monitor_func(func):  # for function annotation
    def wrapper(*args, **kwargs):
        print(func.__name__ + " {")
        ts = time.time()
        try:
            result = func(*args, **kwargs)
            te = time.time()
            print("} ", func.__name__, " finished in ", round((te - ts), 1), " s")
            return result
        except:
            te = time.time()
            print("} ", func.__name__, " failed after ", round((te - ts), 1), " s, ")
            raise

    return wrapper


def plot_res_cxcy(outfile, resCX, resCY, prpX=Amot, prpY=OilR, prpC=pSwi, styls=seris):
    """C is colour, or the property for which data serieses to be ploted"""
    dbg_msg("\n {", 0, endl=" ")
    fig, axes_ = plt.subplots(nrows=1, ncols=1, sharex=False, sharey=False)
    axes = axes_ if isinstance(axes_, (list,)) else [axes_]  # TODO: use this elsewhere

    axp = axes[0]  # if len(prpsY)==1 else axes[0][jj]
    plt.sca(axp)

    rects = []
    legs = []
    for ii, (nam, resX) in enumerate(resCX.items()):
        resY = resCY[nam]
        legs.append(prpC.name + "=" + nam)
        rects.append(prpY.ploT(resX, resY, styls[ii])[0])
    plt.xlabel(prpX.lbl)
    plt.ylabel(prpY.lbl)

    ncols = 2 if len(legs) > 3 else 1
    lgd = fig.legend(
        rects, legs, loc="lower center", prop={"size": fontsiz}, frameon=True, ncol=ncols, bbox_to_anchor=(0.63, 0.97), fancybox=False, shadow=False
    )
    lgd.get_frame().set_edgecolor("w")

    fig.set_size_inches((4 * scalImg * 1, 3 * scalImg * 1))
    fig.tight_layout()
    fig.savefig(outfile, bbox_extra_artists=(lgd,), bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    disp(" }")


def sims_to_cycx(sims, prpX=Amot, prpY=OilR, prpC=pSwi):
    """C is colour, or the property for which data serieses to be ploted"""
    dbg_msg(" *{ ", 0)
    resCX = {}
    resCY = {}
    for sim in sims:
        ci = str(sim.getRes(prpC))
        resCX.setdefault(ci, []).append(sim.getRes(prpX))
        resCY.setdefault(ci, []).append(sim.getRes(prpY))
    disp(" }* ")
    return resCX, resCY


def plot_cyx(outfile, sims, prpX=Amot, prpY=OilR, prpC=pSwi, styls=seris):
    """C is colour, or the property for which data serieses to be ploted"""
    dbg_msg(" **{", 0)
    resCX, resCY = sims_to_cycx(sims, prpX, prpY, prpC)
    plot_res_cxcy(outfile, resCX, resCY, prpX, prpY, prpC, styls)
    disp("}** ")


def cross_diffs(sims1, sims2, prp=OilR, prpC=pSwi):
    # TODO: make use of !
    resC1, _ = sims_to_cycx(sims1, prp, prp, prpC)
    resC2, _ = sims_to_cycx(sims2, prp, prp, prpC)
    difs = {"MD_" + prp.name: [], "MAD_" + prp.name: [], "RMSD_" + prp.name: [], "Slop_" + prp.name: []}
    for ii, resX in enumerate(resC1):
        resY = resC2[ii]

        difs["MD_" + prp.name].append(np.average(resY) - np.average(resX))
        difs["MAD_" + prp.name].append(np.average(np.abs(np.subtract(resY, resX))))
        difs["RMSD_" + prp.name].append(np.sqrt(np.average(np.square(np.subtract(resY, resX)))))
        popt, _pcov = curve_fit(func_linear, resX, resY)
        difs["Slop_" + prp.name].append(popt[0])
    return difs


def plot_cycls(sims=None, prps=None, icycls=None, outfile="relPerms.svg", addSummary=True):
    if icycls is None:
        icycls = [1, 2, 3]
    if prps is None:
        prps = []
    if sims is None:
        sims = []
    disp(f"plot_cycls  >> {Path.cwd()}/{outfile}")
    rects = []
    legs = []
    fig, axes_ = plt.subplots(nrows=len(icycls), ncols=len(prps), sharex=False, sharey=False)
    axes = [axes_] if (len(icycls) == 1) else axes_

    for jj, prp in enumerate(prps):
        for ii, icy in enumerate(icycls):
            axp = axes[ii] if len(prps) == 1 else axes[ii][jj]
            plt.sca(axp)

            rects = []
            legs = []
            for sim in sims:
                gnmSPKwoR1 = sim.getRes_(prp, icy)
                try:
                    datax, datay = gnmSPKwoR1[:, prp.xcol], gnmSPKwoR1[:, prp.icol]
                    pl = prp.ploT(datax, datay, sim.styl, sim, icy, prp.icol)[0]
                    if len(sim.lgnd) and len(sims) > 1:
                        rects.append(pl)
                        legs.append(to_caption(sim.lgnd))
                    if prp.icol2:
                        prp.ploT(datax, gnmSPKwoR1[:, prp.icol2], sim.styl, sim, icy, prp.icol2)
                except Exception as e:
                    alert(f"not enough data for {prp.name} _{prp.icycle}, sim:{sim.lgnd}, resname: {sim.resFile()}: {gnmSPKwoR1}", -1, e)

            plt.ylabel(prp.lbl)
            prp.setXAxis(prp, axp)
        plt.xlabel(prp.xlbl)
    lgart = []
    ncols = 2 if len(prps) % 3 else 3
    if len(legs) < 4 and len(prps) == 1:
        ncols = 1
    plargs = {}
    if len(legs) > 1:
        plargs["bbox_to_anchor"] = (0.63, 0.97) if addSummary else (0.5, 0.97)
        plargs["loc"] = "lower center"
    else:
        plargs["bbox_to_anchor"] = (0.49, 0.97)
    lgd = fig.legend(
        rects, legs, prop={"size": fontsiz}, frameon=True, ncol=ncols, **plargs, fancybox=False, shadow=False
    )  #        #lgd.get_frame().set_alpha(0.9)
    lgd.get_frame().set_edgecolor("w")
    lgart = [lgd]

    if addSummary:
        subtitl = (sims[0].img.netname(mEx)).replace("_", "-")
        phi = sims[0].getRes(pPhi)
        Kab = sims[0].getRes(pKsp)
        FF = sims[0].getRes(pFF)
        if sims[0].mtd.mNam != "Exp":
            subtitl += (
                r"\n" + sims[0].mtd.mNam + r": $\phi$=" + str(round(phi * 1000) / 1000) + ", K=" + str(int(Kab * 1e15)) + "mD, FF=" + str(round(FF * 10) / 10)
            )
        else:
            subtitl += r"\n" + "DNS" + r": $\phi$=" + str(round(phi * 1000) / 1000) + ", K=" + str(int(Kab * 1e15)) + "mD, FF=" + str(round(FF * 10) / 10)
        disp(subtitl.replace("\n", "\t\t"), end="; ")
        lgart = [*lgart, fig.suptitle(subtitl, fontsize=fontsiz, y=1.10, x=0.05, horizontalalignment="left")]

    fig.set_size_inches((4 * scalImg * len(prps), 3 * scalImg * len(icycls) + 0.05 * (len(sims))))
    fig.tight_layout()
    pad = 0.3 if addSummary else 0.2
    fig.savefig(outfile, bbox_extra_artists=lgart, bbox_inches="tight", pad_inches=pad)
    plt.close(fig)


def plot_props_compact(sims=None, prps=None, icycls=None, outfile="relPerms.svg", addSummary=True, returnData=False):
    if icycls is None:
        icycls = [1, 2, 3]
    if prps is None:
        prps = []
    if sims is None:
        sims = []
    disp("{cycl" + str(icycls) + " " + prps[-1].name + " x" + str(len(sims)) + "    >> " + outfile, 0, end=" ")
    rects = []
    legs = []
    fig, axes_ = plt.subplots(nrows=1, ncols=len(prps), sharex=False, sharey=False)
    axes = [axes_]  # if(len(icycls)==1) else axes_
    ret: dict[str, dict[str, np.ndarray]] | None = {} if returnData else None
    ii = 0
    for jj, prp in enumerate(prps):
        axp = axes[ii] if len(prps) == 1 else axes[ii][jj]
        plt.sca(axp)
        for icy in icycls:
            rects = []
            legs = []
            for sim in sims:
                sty = sim.styl
                if icy == 1 and len(icycls) > 1:
                    sty = sM_
                gnmSPKwoR1 = sim.getRes_(prp, icy)
                try:
                    datax = gnmSPKwoR1[:, prp.xcol]
                    datay = gnmSPKwoR1[:, prp.icol]
                    if len(datay) < 2:
                        dbg_msg("Not enough data for plot")
                    rects.append(prp.ploT(datax, datay, sty, sim, icy, prp.icol)[0])
                    if prp.icol2:
                        prp.ploT(datax, gnmSPKwoR1[:, prp.icol2], sty, sim, icy, prp.icol2)
                    lgnd = sim.lgnd
                    if len(icycls) > 1:
                        lgnd += ", cycle " + str(icy)
                    legs.append(to_caption(lgnd))
                    if ret is not None:
                        ret.update({sim.lgnd: {prp.xlbl: datax, prp.lbl: datay}})
                except:
                    print("------- {prp.name} {icy} ----------------------")
                    raise

            plt.ylabel(prp.lbl)
            prp.setXAxis(prp, axp)
        plt.xlabel(prp.xlbl)

    ncols = 2 if len(prps) % 3 else 3
    if len(legs) < 4:
        ncols = 1
    lgd = fig.legend(
        rects, legs, loc="lower center", prop={"size": fontsiz}, frameon=True, ncol=ncols, bbox_to_anchor=(0.63, 0.97), fancybox=False, shadow=False
    )  #    #lgd.get_frame().set_alpha(0.9)
    lgd.get_frame().set_edgecolor("w")

    subtitl = ""
    if addSummary:
        subtitl = (sims[0].img.netname(mEx)).replace("_", "-")
        phi = sims[0].getRes(pPhi)
        Kab = sims[0].getRes(pKsp)
        FF = sims[0].getRes(pFF)
        if sims[0].mtd.mNam != "Exp":
            subtitl += (
                r"\n " + sims[0].mtd.mNam + r": $\phi$=" + str(round(phi * 1000) / 1000) + ", K=" + str(int(Kab * 1e15)) + "mD, FF=" + str(round(FF * 10) / 10)
            )
        else:
            subtitl += r"\n" + "DNS" + r": $\phi$=" + str(round(phi * 1000) / 1000) + ", K=" + str(int(Kab * 1e15)) + "mD, FF=" + str(round(FF * 10) / 10)
        disp(subtitl)

    stitl = fig.suptitle(subtitl, fontsize=fontsiz, y=1.10, x=0.05, horizontalalignment="left")

    fig.set_size_inches((4 * scalImg * len(prps), 3 * scalImg * 1 + 0.05 * (len(sims))))
    fig.tight_layout()
    fig.savefig(outfile, bbox_extra_artists=(lgd, stitl), bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)

    disp("}")
    return ret


def plot_si_sr(simss=None, legs=None, prps=None, outfile="SiSrs.svg"):
    """TODO replace with plot_cyx"""
    if prps is None:
        prps = []
    if legs is None:
        legs = []
    if simss is None:
        simss = [[]]
    dbg_msg("{", 0, endl=" ")
    rects = []  # legs=[]
    fig, axes = plt.subplots(nrows=1, ncols=len(prps), sharex=False, sharey=False)
    for prp in prps:
        plt.sca(axes)

        rects = []
        for sims in simss:
            gnmSPKwoR1 = prp.grab_fn(sims, prp)
            gnmSPKwoR1.append([0.0, 0.0])
            gnmSPKwoR1 = np.transpose(gnmSPKwoR1)
            rects.append(prp.ploT(gnmSPKwoR1[0], gnmSPKwoR1[1] / (prp.unit), sims[0].styl)[0])

        plt.xlabel(prp.xlbl)
        plt.ylabel(prp.lbl)

    ncols = 2 if len(legs) > 3 else 1
    lgd = fig.legend(
        rects, legs, loc="lower center", prop={"size": fontsiz}, frameon=True, ncol=ncols, bbox_to_anchor=(0.63, 0.97), fancybox=False, shadow=False
    )
    lgd.get_frame().set_edgecolor("w")

    fig.set_size_inches((4 * scalImg * len(prps), 3 * scalImg + 0.05 * (len(simss))))
    fig.tight_layout()
    fig.savefig(outfile, bbox_extra_artists=(lgd,), bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)

    disp("}")


def func_linear(x, a, b):
    return a * x + b


def props_dif1faz_plot(simssX=None, simssY=None, legs=None, styls=None, prpsX=None, prpsY=None, outfile="prop1faz.svg"):
    if prpsY is None:
        prpsY = []
    if prpsX is None:
        prpsX = []
    if styls is None:
        styls = []
    if legs is None:
        legs = []
    if simssY is None:
        simssY = [[]]
    if simssX is None:
        simssX = [[]]
    dbg_msg("{", 0, endl=" ")
    disp(
        [
            len(simssY),
            len(simssX),
            len(legs),
            len(styls),
            len(prpsY),
        ]
    )
    rects = []  # legs=[]
    fig, axes_ = plt.subplots(nrows=1, ncols=len(prpsY), sharex=False, sharey=False)
    axes = [axes_] if (len(prpsY) == 1) else axes_
    difs = {}
    for jj, prpY in enumerate(prpsY):
        prpX = prpsX[jj]
        axp = axes[jj]  # if len(prpsY)==1 else axes[0][jj]
        plt.sca(axp)

        rects = []
        legs = []
        difs.update({"MD_" + prpY.name: [], "MAD_" + prpY.name: [], "RMSD_" + prpY.name: [], "Slop_" + prpY.name: []})
        for ii, simImgs in enumerate(simssY):
            sty = styls[ii]
            disp(prpX.name + " X: " + str([sim.getRes(prpX) for sim in simssX[ii]]) + str(len(simssX[ii])) + " x " + simImgs[0].mtd.mNam)
            disp(prpY.name + " Y: " + str([sim.getRes(prpY) for sim in simImgs]) + str(len(simImgs)) + " x " + simImgs[0].mtd.mNam)
            gnmSP_x = [np.log10(max(sim.getRes(prpX), prpX.small)) for sim in simssX[ii]]
            gnmSP_y = [np.log10(max(sim.getRes(prpY), prpY.small)) for sim in simImgs]

            difs["MD_" + prpY.name].append(np.average(gnmSP_y) - np.average(gnmSP_x))
            difs["MAD_" + prpY.name].append(np.average(np.abs(np.subtract(gnmSP_y, gnmSP_x))))
            difs["RMSD_" + prpY.name].append(np.sqrt(np.average(np.square(np.subtract(gnmSP_y, gnmSP_x)))))
            popt, _pcov = curve_fit(func_linear, gnmSP_x, gnmSP_y)
            difs["Slop_" + prpY.name].append(popt[0])

            if not len(outfile):
                continue  ########################
            legs.append(simImgs[0].mtd.mNam)
            rects.append(prpY.ploT(gnmSP_x, gnmSP_y, sty)[0])

            plt.xlabel("log " + prpX.lbl + ",  " + simssX[ii][0].mtd.mNam)
            plt.ylabel("log " + prpY.lbl + " ")
            if ii == 1:
                for i, x in enumerate(gnmSP_x):
                    axp.annotate(simssX[ii][i].lgnd, (x, gnmSP_y[i]), fontsize=10).set_alpha(0.4)
    if len(outfile):
        ncols = 2 if len(legs) > 3 else 1
        lgd = fig.legend(
            rects, legs, loc="lower center", prop={"size": fontsiz}, frameon=True, ncol=ncols, bbox_to_anchor=(0.63, 0.97), fancybox=False, shadow=False
        )
        lgd.get_frame().set_edgecolor("w")

        fig.set_size_inches((4 * scalImg * len(prpsY), 3 * scalImg * 1))
        fig.tight_layout()
        fig.savefig(outfile, bbox_extra_artists=(lgd,), bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    disp("}")
    return difs


def run_plot_xnm1fs(
    workdir, mtds=None, inp=None, pltNam="KabsFF", tag="", runfsims=True, forceRun=False, propsX=None, propsY=None, SimType=FlowSim, hdrs=models.mhds
):
    """Run cnflow-compatible of network models
    mtds[0] is x axis, mtd[1] is y when returning avg dif"""
    if propsY is None:
        propsY = []
    if propsX is None:
        propsX = []
    if inp is None:
        inp = {}
    if mtds is None:
        mtds = [mDS, mSN, mCN]
    disp("============ run_plot_xnm1fs ===============")
    pwd_main = Path.cwd()
    try:
        os.chdir(workdir)
    except OSError:
        dbg_msg(f"Error cannot get into {workdir}/, from {Path.cwd()}")
        sys.exit(-1)

    inp.setdefault("Cycle1", "")
    simss = []
    difs = {}
    imgs = get_pwd_images(hdrs)
    ensure(
        len(imgs), f"Error: no .mhd images found in {workdir}, pwd:{Path.cwd()}", 1
    )  # raise ValueError('Error: no .mhd images found in ' + workdir); return -1

    mrkrs = copy.deepcopy([sEX, sSN, sE2, sXN, sCN, sE8, sE7])
    mrkrs[0].markr = "o"
    mrkrs[1].markr = "s"
    mrkrs[2].markr = "*"
    mrkrs[3].markr = "x"
    mrkrs[4].markr = "^"
    mrkrs[0].ms = 2
    mrkrs[0].lw = 1
    for ii in range(1, len(mrkrs)):
        mrkrs[ii].ms = 4
        mrkrs[ii].lw = 0
    inpt = copy.deepcopy(inp)
    inpt["UpscaleBox"] = "0. 1."
    inpt["AlterContAng"] = "4   30  50  -0.2    -3.   rand   0."
    simsAll = []
    legsI72 = []
    for jj, mtd in enumerate(mtds):
        simss.append([])
        legsI72.append(mtd.mNam)
        for img in imgs:
            lgn = ", " + mtd.mNam if len(mtds) > 1 else ""
            simtag = tag
            simsAll.append(SimType(simtag, img.name + lgn, img, mtd, mrkrs[jj], inpt.copy(), force_rerun=forceRun))
            simss[jj].append(simsAll[-1])
        disp("Sims: " + str([sim.img.name for sim in simss[jj]]))
        if runfsims:
            run_par(simss[-1], nPyProc)

    simssX = [simss[0] for _ in mtds]  # mtd 0 is base
    plnam = "svg/" + pltNam + "_" + tag + ".svg" if len(pltNam) else ""
    disp(plnam + "******************************")
    if propsX:
        if len(plnam):
            mkdr("./svg")
        difs = props_dif1faz_plot(simssX, simss, legsI72, mrkrs, propsX, propsY, outfile=plnam)

    try:
        os.chdir(pwd_main)
    except OSError:
        dbg_msg(f"Error cannot get back to {pwd_main}")
        sys.exit(-1)
    ensure(pwd_main == Path.cwd(), f"pwd: {Path.cwd()}")

    return (simss, difs)


def run_sensitivity_xnmsp(
    workdir, mtds=None, key1="", rang1=None, key2="", rang2=None, nDiv=5, bef1="", aft1="", bef2="", aft2="", inp=None, pltNam="Sensitivity", runfsims=True
):
    if inp is None:
        inp = {}
    if rang2 is None:
        rang2 = [0, 1.0]
    if rang1 is None:
        rang1 = [0, 1.0]
    if mtds is None:
        mtds = [mDS, mSN, mCN, mXP]
    inp = {}
    MDs = {}
    MADs = {}
    Slops = {}
    RMSDs = {}
    propsY = [pKsp, pFF]
    for prpY in propsY:
        MDs[prpY.name] = [[] for i in range(nDiv + 1)]
        MADs[prpY.name] = [[] for i in range(nDiv + 1)]
        Slops[prpY.name] = [[] for i in range(nDiv + 1)]
        RMSDs[prpY.name] = [[] for i in range(nDiv + 1)]
    X2 = []
    X1 = []
    disp(f"lens: propsY: {len(propsY)},  MDs[0]: {len(MDs[propsY[0].name])}")
    for ii in range(nDiv + 1):
        Yval = rang1[0] + (rang1[1] - rang1[0]) * ii / (nDiv + 1e-64)
        keyv1 = str(Yval)
        X1.append(Yval)
        X2 = []
        inp[key1] = bef1 + " " + keyv1 + " " + aft1
        for jj in range(nDiv + 1):
            Xval = rang2[0] + (rang2[1] - rang2[0]) * jj / (nDiv + 1e-64)
            keyv2 = str(Xval)
            inp[key2] = bef2 + " " + keyv2 + " " + aft2
            disp(inp)
            _simss, difs = run_plot_xnm1fs(
                workdir, mtds, inp, tag=key1 + keyv1 + "_" + key2 + keyv2, runfsims=runfsims, propsX=propsY, propsY=propsY, pltNam=""
            )
            disp("difs: ")
            disp(difs)
            X2.append(Xval)
            for prpY in propsY:
                MDs[prpY.name][ii].append(difs["MD_" + prpY.name][1])
                MADs[prpY.name][ii].append(difs["MAD_" + prpY.name][1])
                Slops[prpY.name][ii].append(difs["Slop_" + prpY.name][1])
                RMSDs[prpY.name][ii].append(difs["RMSD_" + prpY.name][1])

    for prpY in propsY:
        fig, axes = plt.subplots(nrows=2, ncols=2, figsize=(15, 13), dpi=80, sharex=False, sharey=False)
        disp("lens:" + str(len(X1)) + " " + str(len(X2)) + " " + str(len(MDs[prpY.name])) + " " + str(len(MDs[prpY.name][0])) + " ")

        ax = axes[0][0]
        plt.sca(ax)
        ax.set_title("mean absolute difference")
        cpl = ax.contourf(X2, X1, MADs[prpY.name])
        plt.clabel(cpl, inline=True, fontsize=10)
        plt.colorbar(cpl)
        plt.xlabel(key2)
        plt.ylabel(key1)
        ax = axes[0][1]
        plt.sca(ax)
        ax.set_title("mean difference")
        cpl = ax.contourf(X2, X1, MDs[prpY.name])
        plt.clabel(cpl, inline=True, fontsize=10)
        plt.colorbar(cpl)
        plt.xlabel(key2)
        plt.ylabel(key1)
        ax = axes[1][0]
        plt.sca(ax)
        ax.set_title("root mean square difference")
        cpl = ax.contourf(X2, X1, RMSDs[prpY.name])
        plt.clabel(cpl, inline=True, fontsize=10)
        plt.colorbar(cpl)
        plt.xlabel(key2)
        plt.ylabel(key1)
        ax = axes[1][1]
        plt.sca(ax)
        ax.set_title("slope")
        cpl = ax.contourf(X2, X1, Slops[prpY.name])
        plt.clabel(cpl, inline=True, fontsize=10)
        plt.colorbar(cpl)
        plt.xlabel(key2)
        plt.ylabel(key1)
        plname = workdir + "/svg/" + pltNam + "_" + prpY.name + "_" + key1 + "_" + key2 + ".svg"
        disp(plname + "******************************")
        fig.savefig(plname, bbox_inches="tight")
        plt.close(fig)


def run_plot_xnm_scannings(
    mtd, pltPrfix, img, prp1s, prp2s, inp, prp1=CAdv, prp2=pSwi, doRun=True, doPlot=True, nImgs=2, clrSchem=sriGrad, addExp=False
):  # sync with all_run_xnm_2f
    inpt = copy.deepcopy(inp)
    inpt.setdefault("UpscaleBox", "0.2 0.9")
    if len(autoInitCA):
        inpt.setdefault("InitContAng", autoInitCA)  # disp({'autoInitCA':autoInitCA})
    inpt.setdefault("NetworkDir", img.netDir)
    inpt.setdefault("Cycle2", "1.    -1.0E+05     0.02       T        T")
    inpt.setdefault("Cycle1_BC", "T     F       T       T      DP    1.  1.")
    inpt.setdefault("Cycle2_BC", "T     F       T       T      DP    1.  1.")

    simsAll = []
    simsI72 = []
    simsI72Pc = []
    simsI72Pc0_ = []
    iClr = 0
    simsSwI72 = []
    legsI72 = []
    disp("runPlotXNMSca_CAs:" + str(prp1s) + " _Swis:" + str(prp2s))
    for jj, CAp in enumerate(prp1s):
        simsSwI72.append([])
        legsI72.append(prp1.name + "=" + str(CAp))
        for ii, Swi in enumerate(prp2s):
            simtag = ""
            lgnd = img.name if nImgs > 1 else ""
            if len(prp2s) > 1 and prp2.name != pNon.name:
                lgnd += (",  " if len(lgnd) else "") + prp2.lbl + f"={Swi} "
            if len(prp1s) > 1 and prp1.name != pNon.name:
                lgnd += (",  " if len(lgnd) else "") + prp1.lbl + "=" + str(CAp) + " "
            if len(lgnd) < 1:
                lgnd += mtd.mNam
            sim = _SimTyp(simtag, lgnd, img, mtd, clrSchem[jj][ii], inpt)
            sim.setInpTag(prp1, CAp)
            sim.setInpTag(prp2, Swi)  #  also add tags
            sim.tag = simtag
            simsAll.append(sim)

            simsI72.append(sim)
            if ii % 3 == 0:
                simsI72Pc.append(sim)
            if ii == 0:
                simsI72Pc0_.append(sim)
            simsSwI72[jj].append(sim)

            iClr += 1

    if doRun:
        run_par(simsI72, nPyProc)
        for sim in simsAll:  # this is to load the resFile while we are in the right dir
            phi = sim.getRes_(pPhi)
            ensure(phi > 0.01 and phi < 0.9, f"porosity (={phi}) check failed")

    if doPlot:
        pltTag = mtd.mNam
        plot_cycls(simsI72Pc, plPcKrRI, icycls=plIcycls, outfile=f"{pltPrfix}_Swis_{pltTag}_PcKrRI.svg")
        if len(prp2s) > 1:
            plot_props_compact(simsI72Pc, [plPc], icycls=plIcycls, outfile=f"{pltPrfix}_Swis_{pltTag}_PcCmpct.svg", addSummary=False)
            plot_props_compact(simsI72Pc, [plKr], icycls=plIcycls, outfile=f"{pltPrfix}_Swis_{pltTag}_KrCmpct.svg", addSummary=False)

            if addExp:
                simsSwI72.append([FlowSim("", "", img, mEx, sEX, {})])
                legsI72.append("Experiment")
            plot_si_sr(simsSwI72, legsI72, [pSgr], outfile=f"{pltPrfix}_Swis_{pltTag}_SiSr.svg")

        simsI72Pc0 = simsI72Pc0_
        plot_props_compact(simsI72Pc0, [plPc], icycls=plIcycls, outfile=f"{pltPrfix}_Swi0_{pltTag}_PcCmpct.svg", addSummary=False)
        plot_props_compact(simsI72Pc0, [plKr], icycls=plIcycls, outfile=f"{pltPrfix}_Swi0_{pltTag}_KrCmpct.svg", addSummary=False)
        plot_props_compact(simsI72Pc0, [plRI], icycls=plIcycls, outfile=f"{pltPrfix}_Swi0_{pltTag}_RICmpct.svg", addSummary=False)

    return simsAll


@monitor_func
def all_run_xnm_2f(
    workdir,
    mtds=None,
    prp1ss=None,
    prp2ss=None,
    prp1=CAdv,
    prp2=pSwi,
    cmnds=None,
    inp=None,
    hdrs=None,
    subHdrs=None,
    plotCostum=None,
    pltArgs=None,
    doRun=True,
    doPlot=False,  # noqa: ARG001
    summerize=None,
    nSubRuns=0,
    ppF=None,
):
    """serialize simulation list and run in parallel at once"""
    if pltArgs is None:
        pltArgs = [{}]
    if subHdrs is None:
        subHdrs = []
    if hdrs is None:
        hdrs = []
    if inp is None:
        inp = {}
    if cmnds is None:
        cmnds = [nil_fn]
    if prp2ss is None:
        prp2ss = [[0.0]]
    if prp1ss is None:
        prp1ss = [[[30, 60]]]
    if mtds is None:
        mtds = [mDS, mSN, mXP, mCN]
    pwd_main = Path.cwd()
    try:
        os.chdir(workdir)
    except OSError:
        dbg_msg("Error cannot get into " + workdir + "/, from " + Path.cwd())
        sys.exit()
        return None

    disp("prp1:" + prp1.name + ("" if doRun else " doRun:False"))

    simsAl = []
    simsD4 = []
    imgs = get_pwd_images(hdrs)

    """ ***** serialize  cmd mtd img ****** """
    for ig, img in enumerate(imgs):
        simsD4.append([])
        simsD3 = simsD4[-1]
        for mtd in mtds:
            simsD3.append([])
            simsD2 = simsD3[-1]
            for ii, cmnd in enumerate(cmnds):
                inpt = inp.copy()
                if nSubRuns:
                    inpt["stage1"] = str(nSubRuns) + " " + img.name + ("" if ig >= len(subHdrs) else " " + (" ".join(map(str, subHdrs[ig]))))
                cmnd(inpt)
                if len(prp1ss[ii]) == 0:
                    prp1ss[ii] = prp1ss[ii - 1]
                if len(prp2ss[ii]) == 0:
                    prp2ss[ii] = prp2ss[ii - 1]
                clrs = get_ca_sw_colors_hsv(len(prp1ss[ii]), len(prp2ss[ii]))
                sims = run_plot_xnm_scannings(mtd, "", img, prp1ss[ii], prp2ss[ii], inpt, prp1, prp2, False, False, len(imgs), clrs)
                simsD2.append(sims)
                simsAl.extend(sims)

    disp(("len sims:", len(simsD4), len(simsD4[0]), len(simsD4[0][0]), len(simsD4[0][0][0])))

    if doRun:
        run_par(simsAl, nPyProc)

    if doRun and ppF:
        disp("========= ppF ==========")
        for sim in simsAl:
            ppF(sim)

    for sim in simsAl:  # load the resFile while we are in the right dir
        phi = sim.getRes_(pPhi)
        ensure(phi > 0.01 and phi < 0.9, f"porosity (={phi}) check failed for sim {sim.tag}")

    if plotCostum:
        mkdr("./svg")

        if len(prp1ss) * len(prp2ss) > 0:
            for ig, img in enumerate(imgs):
                for jj, mtd in enumerate(mtds):
                    for ic, _ in enumerate(cmnds):
                        plotCostum(np.ravel(np.array(simsD4[ig][jj][ic][:])).tolist(), img.name, mtd.mNam, prp1.name, level=1, **pltArgs[ic])

        if len(imgs) > 1:
            for ip in range(len(simsD4[0][0][0])):
                for jj, mtd in enumerate(mtds):
                    for ic, _ in enumerate(cmnds):
                        plotCostum([simsD4[ig][jj][ic][ip] for ig in range(len(simsD4))], prp1.toTag(prp1ss[ic][ip]), mtd.mNam, "Image", level=1, **pltArgs[ic])

        if len(mtds) > 1:
            for ig, img in enumerate(imgs):
                for ip in range(len(simsD4[0][0][0])):
                    for ic, _ in enumerate(cmnds):
                        plotCostum(
                            [simsD4[ig][jj][ic][ip] for jj, mtd in enumerate(mtds)], img.name, prp1.toTag(prp1ss[ic][ip]), "Model", level=1, **pltArgs[ic]
                        )

    if summerize:
        try:
            sim3D = [[[UncSim("", sims=xs) for xs in xss] for xss in xsss] for xsss in simsD4]
            for ii, _ in enumerate(cmnds):
                summerize(np.ravel(np.array(sim3D)[:, :, ii]).tolist(), prp1, prp1ss[ii], **pltArgs[ii])
        except Exception as e:
            dbg_msg(f"Error in summarize: {e}", 0, nSkipTrace=2)

    try:
        os.chdir(pwd_main)
    except OSError:
        alert(f"something wrong with {pwd_main}", -1)
    return simsD4  # simsD4[imgs][mtds][cmnds/prp2s][prp1s]


def mk_sensii(cmnds, prp1, prp1ss, prp2, prp2ss, mhds, kwargs, subHdrs=None, subkwargs=None):
    if subkwargs is None:
        subkwargs = {}
    if subHdrs is None:
        subHdrs = []
    print("\n####################################\n")
    print("kwargs:", kwargs)
    workdir = "sensi_" + prp1.name
    mkdr(workdir)
    disp((prp1.name, prp1ss, " ", prp2.name, prp2ss))
    if subHdrs:
        all_run_xnm_2f(workdir, [mSN], prp1ss, prp2ss, prp1, prp2, cmnds, hdrs=subHdrs[0], **subkwargs)
        return all_run_xnm_2f(workdir, [mSN], prp1ss, prp2ss, prp1, prp2, cmnds, hdrs=mhds, subHdrs=subHdrs, **kwargs)
    return all_run_xnm_2f(workdir, [mSN], prp1ss, prp2ss, prp1, prp2, cmnds, hdrs=mhds, **kwargs)
