"""pore-scale models and parameters, Contents: Seri, Prop, Method, VoxImg and FlowSom  classes"""
from __future__ import annotations

import argparse
import colorsys
import copy
import statistics as st
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from .msrc import DbgMsg, disp, ensure
from .msutils import (
    grepFloatInRes,
    grepOilR,
    grepSiSr,
    grepSor,
    grepSwi,
    grepTableInRes,
    runCpDNS1f,
    runPar,
    runSKE,
    runSkip,
    runXNFlow,
)
from .xpm_utils import runXPM

parser= argparse.ArgumentParser()
def _str_to_bool(s):
    """Convert string to bool (in argparse context)."""
    assert s.lower() in ["true", "false", "0", "1"], f"Need bool; got {s}"
    return {"true": True, "false": False, "1": True, "0": False}[s.lower()]

def boolArg(name, default=False):
    """Add a boolean argument to an ArgumentParser instance."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(f"--{name}", nargs="?", default=default, const=True, type=_str_to_bool)
    group.add_argument(f"--no{name}", dest=name, action="store_false")
def boolArgs(names, default=False):
    for nam in names: boolArg(nam,default)
def strArg(name, default=""):  parser.add_argument(f"--{name}", default=default)
def parseArgs():
    strArg("sens") # sensitivity params
    strArg("rTg") # rename (retag) prop
    strArg("mhds") # mhd/image names
    boolArgs(("DNS","SKE","snsi","si")) # run DNS, SNExtract or flow seni(tivity)
    args = parser.parse_args()
    args.sens=args.sens.split(",")
    return args


numenclature={}
def toCaption(nam):
    for di,dv in numenclature.items():
        nam = nam.replace(di,dv)
    return nam



""" ============= Plot helpers ============== """


fontsiz=14 ;  scalImg=1.5
plt.rcParams.update({"font.family":"serif", "font.size":fontsiz})
plt.rc("legend",fontsize=fontsiz)
mpl.mathtext.SHRINK_FACTOR = 0.8

PatchDEA=False

class Seri: # a plot line/series style (sty)
    markr = "";  clrW = "#ff0000"

    def __init__(my, markr="+", clr="#bbbbbb", mw=1, ms=5, ls="-",lw=2, dsh=None, al=0.9):
        my.markr = markr  # marker
        my.clrW = clr  # colour
        my.mw = mw  # marker width
        my.ms = ms  # marker size
        my.ls = ls  # line style
        my.lw = lw  # line width
        my.mclr = clr  # marker colour
        my.dsh = dsh  # dash
        my.al = al  # alpha

def seriof(redness, ls="-"):
    """ scalar to series conversion"""
    rgb = colorsys.hsv_to_rgb(0.63-redness*0.62, 0.9, 255)  # h=0.6666666 is blue # h=0. is red
    factor = (max(rgb)*3)/(sum(rgb)+2*max(rgb))
    rgb = tuple([factor*x for x in rgb])
    hx1 = f"#{int(rgb[0]):02x}{int(rgb[1]):02x}{int(rgb[2]):02x}"
    hx2 = f"#{int(rgb[0]*0.5):02x}{int(rgb[1]*0.5):02x}{int(rgb[2]*0.5):02x}"
    wst = Seri("", hx1, mw=1, ms=3, ls=ls, lw=2, clr=hx2)
    wst.markr = mpl.markers.MarkerStyle("^").get_path().transformed(mpl.transforms.Affine2D().scale(0.6,1.).rotate_deg(redness*180-90))  # python ><^ are aggly and wrong
    return wst

try : #'plot series styles'
    #     marker    colour maerke-width,size line-style  line-width
    sSN=Seri("+",  "#1b6fdf",   mw=1, ms=5,  ls="-" ,   lw=2 )             # SNM
    sXN=Seri("$*$","#00bfbf",   mw=1, ms=5,  ls="--",   lw=2, dsh=[6,3])   # XPM
    sPN=Seri("x",  "#c72e3a",   mw=1, ms=5,  ls="-.",   lw=2, dsh=[6,2,2,2])
    sEX=Seri("x",  "#000000",   mw=3, ms=10, ls="None", lw=0 ) # experiment
    sE1=Seri("o",  "#5500bb",   mw=1, ms=5,  ls="-" ,   lw=2 )
    sE2=Seri("s",  "#00ff55",   mw=1, ms=5,  ls="-" ,   lw=2 )
    sE3=Seri("v",  "#bb00ff",   mw=1, ms=5,  ls="-" ,   lw=2 )
    sE4=Seri("^",  "#ff99bb",   mw=1, ms=5,  ls="-" ,   lw=2 )
    sE5=Seri("d",  "#b5a12b",   mw=1, ms=5,  ls="-" ,   lw=2 )
    sE6=Seri("D",  "#e2b03d",   mw=1, ms=5,  ls="-" ,   lw=2 )
    sE7=Seri("<",  "#784f3c",   mw=1, ms=5,  ls="-" ,   lw=2 )
    sE8=Seri(">",  "#af70da",   mw=1, ms=5,  ls="-" ,   lw=2 )
    sAn=Seri("D",  "#11e1e1",   mw=1, ms=5,  ls="--",   lw=2, dsh=[6,2])  # Analytical
    sCN=Seri("x",  "#bb4570",   mw=1, ms=5,  ls="-.",   lw=3, dsh=[6,3])  # Classical net
    sM_=Seri("x",  "#bbbbbb",   mw=0, ms=0,  ls="-" ,   lw=2.5, al=0.5)   # Drainage cycle

    seris = [sXN,sSN,sPN,sE1,sE2,sE3,sE4,sE5,sE6,sE7,sE8, sPN,sE1,sE2,sE3,sE4,sE5,sE6,sE7,sE8, sPN,sE1,sE2,sE3,sE4,sE5,sE6,sE7,sE8, ]

    sriGrad = [sXN,sSN,sE1,sE2,sE3,sE4,sE5,sE6,sE7,sE8,sPN, sXN,sE1,sE2,sE3,sE4,sE5,sE6,sE7,sE8,sPN, sXN,sE1,sE2,sE3,sE4,sE5,sE6,sE7,sE8,sPN, ]

    serisL = copy.deepcopy(sriGrad)
    for sri in serisL :     sri.ls="-" ;   sri.ms=1  ;   sri.lw=2 ;  sri.mw=0.5
except: raise

def getColorGradxy(alpha=None, linst=None, dshs=None, linwt=None,ms=1, mw=0.5) :
    if linwt is None:
        linwt = [1.5, 1.0, 1.5]
    if dshs is None:
        dshs = [[3, 1], [], [3, 1, 1, 1]]
    if alpha is None:
        alpha = [0.8, 1.0, 0.8]
    linst = ["--", "-", "-."] if linst is None else  linst
    sriGradxy=[copy.deepcopy(sriGrad),copy.deepcopy(sriGrad),copy.deepcopy(sriGrad),]
    for jj,sriG in enumerate(sriGradxy) :
        for sri in sriG :
            sri.ls=linst[jj] ;   sri.lw=linwt[jj] ;   sri.dsh=dshs[jj] ;   sri.ms=ms  ;  sri.mw=mw
    return sriGradxy

def getCASwColorsHSV(nCA=5,nSw=3,dshs=None) :
    """The inner loop has gradient in thickness and alpha, for Swi, outer has gradient in color range, for CA"""
    if dshs is None:
        dshs = [(1, 0), (1, 1), (5, 2), (1, 2), (5, 5)]
    sriGradxy=[]
    for jj in range(nCA) :
        sriGradxy.append([])
        for ii in range(nSw):  sr=seriof(jj/(nCA-1+0.01));  sr.dsh=dshs[ii%len(dshs)];  sriGradxy[jj].append(sr)
    return sriGradxy



class ploT: # plot functor wrpping pyplot.plot, with optional uncertainty  handling for UncSim class
    errbar=False
    def __init__(my, plot = plt.plot):
        my.ploT = plot

    def __call__(my, datax, datay, sty: Seri, sim=None, prp=None, icy=0, icol=0) :
        # return my.ploT(datax,datay, color=sty.clrW,linestyle=sty.ls,linewidth=sty.lw, marker=sty.markr,markeredgewidth=sty.mw, markeredgecolor=sty.mclr,ms=sty.ms, alpha=sty.al,dashes=sty.dsh)
        if isinstance(sim,(UncSim,)) and len(sim.sims)>=3: # add uncertainty range
            if my.errbar:
                xrf_ = sim.getRes_(prp,icy,varI="bgn")
                xy1_ = sim.getRes_(prp,icy,varI="2nd");  xy1 = xy1_[~np.isnan(xy1_)[:,icol]]
                xy2_ = sim.getRes_(prp,icy,varI="end");  xy2 = xy2_[~np.isnan(xy2_)[:,icol]]
                xrf =  xrf_[~np.isnan(xy1_)[:,icol]][:,prp.xcol];    yrf = xrf_[~np.isnan(xy1_)[:,icol]][:,icol]
                eux = (xrf-xy1[:,prp.xcol]);    euy = (yrf-xy1[:,icol])/prp.unit
                xrf =  xrf_[~np.isnan(xy2_)[:,icol]][:,prp.xcol];    yrf = xrf_[~np.isnan(xy2_)[:,icol]][:,icol]
                elx = (xy2[:,prp.xcol]-xrf);    ely = (xy2[:,icol]-yrf)/prp.unit

                plt.errorbar(xrf, yrf/prp.unit, yerr=[euy,ely], xerr=[eux,elx], color=sty.clrW,
                marker=None,  alpha=sty.al)
            varIs=["2nd","bgn","end"]
            for pm in (1,2):
                xy1 = sim.getRes_(prp,icy,varI=varIs[pm-1]);  xy1 = xy1[~np.isnan(xy1)[:,icol]]
                xy2 = sim.getRes_(prp,icy,varI=varIs[pm-0]);  xy2 = xy2[~np.isnan(xy2)[:,icol]]
                xf = np.concatenate((xy1[:,prp.xcol], xy2[::-1,prp.xcol]))
                yf = np.concatenate((xy1[:,icol]    , xy2[::-1,icol]))
                if my.ploT==plt.semilogy:
                    yf=np.array([max(yi,prp.small) for yi in yf])
                plt.fill(xf, yf/prp.unit, sty.clrW+sim.alpha)
            if my.ploT in (plt.semilogx, plt.loglog):  plt.xscale("log", nonpositive="clip")
            if my.ploT in (plt.semilogy, plt.loglog):  plt.yscale("log", nonpositive="clip")
        if my.ploT==plt.semilogy:
            datay=np.array([max(yi,prp.small) for yi in datay])
        dsh_kw = {"dashes": sty.dsh} if sty.dsh is not None else {}
        return my.ploT(datax, datay/prp.unit, color=sty.clrW, linestyle=sty.ls, linewidth=sty.lw, marker=sty.markr,
                       markeredgewidth=sty.mw, markeredgecolor=sty.mclr, ms=sty.ms, alpha=sty.al, **dsh_kw)





""" ============= Methods ============== """
AllMtds={}
class Method: # this stands for simulation/.. method
    def __init__(my, name, styl, cmdapp, outsfx="", netsfx="", runSim=runXNFlow, resPrefix=None, args=None):
        my.setName(name)
        my.mtdstyl = styl
        my.app = cmdapp
        my.outsfx = outsfx
        my.netsfx = netsfx # without .xmf, these are used in runSim=runXNFlow
        my.runSim = runSim # called from FlowSim.runSim()
        if resPrefix is not None:
            my.resPrefix = resPrefix
        my.args = {} if args is None else args  # simulation and arguments

    def setName(my, name):
        my.mNam = name # use in serious stuff!
        my.name = name # use in IO/logging!
        AllMtds[name]=my
        my.resPrefix = f"results{name}/" # resultsSNM/ etc

    def simArgs(my):
        return {"app": my.app, "resDir": my.resPrefix, **my.args}

    def copy(my, name):
        cp = copy.deepcopy(my)
        cp.setName(name)
        return cp


try :
    #'Simulation models'
    mEx = Method("Exp",sE1, cmdapp=""      , outsfx=         ".tsv", resPrefix="Exp/", runSim=runSkip)
    mDS = Method("DNS",sAn, cmdapp=""      , outsfx="_relPerms.tsv", resPrefix="DNS/", runSim=runCpDNS1f)
    mCN = Method("CNM",sCN, cmdapp="cnflow", outsfx="_upscal.tsv", netsfx="Net")  # EXP:
    mSN = Method("SNM",sSN, cmdapp="scalor", outsfx="_upscal.svg")
    mXP = Method("XPM",sXN, cmdapp="xpm"   , outsfx="_upscal.tsv", runSim=runXPM)
    mDy = Method("DSY",sAn, cmdapp=""      , outsfx="_relPermsY.tsv", resPrefix="DNS/", runSim=runCpDNS1f, args={"axs":"Y"})  # EXP:
    mDz = Method("DSZ",sAn, cmdapp=""      , outsfx="_relPermsZ.tsv", resPrefix="DNS/", runSim=runCpDNS1f, args={"axs":"Z"})  # EXP:
    mAn = Method("Anl",sAn, cmdapp="")

    # pre-processing /network extraction
    mSK = Method("SNE",sSN, cmdapp="skelor"   , resPrefix="SKE/", runSim=runSKE)
    mNE = Method("PNE",sSN, cmdapp="pnextract", resPrefix="PNE/", runSim=runSKE)
except: raise






""" ============= class VoxImg ============== """


class VoxImg:
    def __init__(my, name, netDir="../../SKE"):
         my.name = str(name)
         my.expImg = str(name)
         my.netDir = str(netDir) #  =imgDir or networks dir
    def netname(my, mtd):
        #DbgMsg(f"vxl Img, for mtd: {mtd.mNam},  netname: {my.name}{mtd.netsfx}", 2)
        return my.name+mtd.netsfx

mhds=[] # set this manually to avoid looking for .mhd files
def getPWDImages(hdrs=None):
    if not hdrs and len(mhds): hdrs=mhds
    imgs=[]
    try:
        if len(hdrs)>0 : imgs = [VoxImg(f[0:-4] if f[-4]=="." else f) for f in hdrs ] #[0:-4]+'.msm'
        else         :
            imgs = [VoxImg(p.name[0:-4]) for p in sorted(Path().iterdir()) if len(p.name)>4 and p.name[-4:]==".mhd" and Path(f"{p.name[0:-4]}/{p.name}").is_file() ]
            for img in imgs : img.netDir=f"../{img.name}" # used when running AllRunImageNEPar
        disp(f"Images:  {[f.name for f in imgs]!s}, dir: {Path.cwd()}")
    except OSError as e:
        DbgMsg(f"No images found in {Path.cwd()}");  disp(e)
    return imgs



""" ============= Prop(ertie)s ============== """

AllPrps={}
class Prop:
    valBfor="" # input keyword before values
    valAftr="" # input keyword post values
    nSkip=0  # nSkipLines/words before val, used in getRes...
    def __init__(my, name, lbl, dscr, Dy=None, kywrd="", endKy=";"):
        if Dy is None:
            Dy = [0.0, 1.0]
        my.name = name    # instance variable unique to each instance
        my.lbl = lbl
        my.dscr= dscr
        my.xlbl = "$S_w$"
        my.ploT = ploT(plt.plot)
        my.grpFunc = grepTableInRes # ideally shall be called through FlowSim.getRes
        my.xcol = 0;       my.icol = 0;    my.icol2 = 0 # icol=0 indicate scalarness (not array)
        my.unit = 1.;      my.small = 1e-15
        my.Dx = [0.,1.];   my.Dy = Dy
        my.setXAxis = Prop.xAtBorder # set ylim xlim range
        my.kywrd = kywrd if kywrd else name
        my.endKy = endKy;  my.filExt = ""
        my.icycl = 0 # mutable
        my.setFunc = None
        AllPrps[name] = my

    def setLogy(my,Dy=None):
        my.ploT.ploT= plt.semilogy
        my.Dy=Dy if Dy is not None else [0.001,1.]
        my.setXAxis = Prop.xAtBorder

    def setLinear(my,Dy=None):
        my.ploT.ploT= plt.plot
        my.Dy=Dy if Dy is not None else [0.,1.]

    def __str__(my): return my.name + (f"-cycle{my.icycl!s}" if my.icycl else "")#+' ky:'+my.kywrd
    def isArray(my): return my.icol

    def xAtYzero (my,ax) :
        ax.spines["bottom"].set_alpha(0.8);  ax.spines["left"].set_alpha(0.8)
        ax.spines["top"].set_color("none");  ax.spines["right"].set_color("none")
        ax.set_alpha(0.8)
        ax.spines["bottom"].set_position(("data", 0))
        if my.Dy[0]<my.Dy[1]: plt.ylim(my.Dy[0],my.Dy[1])
        if my.Dx[0]<my.Dx[1]: plt.xlim(my.Dx[0],my.Dx[1])

    def xAtBorder (my,ax) :
        ax.spines["bottom"].set_alpha(0.8);  ax.spines["top"].set_alpha(0.8)
        ax.spines["right"].set_alpha(0.8);   ax.spines["left"].set_alpha(0.8)
        ax.set_alpha(0.8)
        if my.Dy[0]<my.Dy[1]: plt.ylim(my.Dy[0],my.Dy[1])
        if my.Dx[0]<my.Dx[1]: plt.xlim(my.Dx[0],my.Dx[1])

    def __hash__(my):      return hash(my.name) # for using prop as dict key
    def __eq__(my, other): return my.name == other.name
    def __ne__(my, other): return not(my == other)
    def toTag(my, val):
        if isinstance(val,(list,np.ndarray)):  return my.name+"".join(map(str,val))
        return my.name+str(val)

try : #'Props' # to make it a class named `Proptis``

    pNon =Prop("",   "Property",              "Description")
    plPc =Prop("Pc",r"$P_c/\sigma$ $(10^5/m)$","curvature (10^5/m)",[-10.,20.]); plPc.icol=1;  plPc.unit=0.03*100000 ; plPc.setXAxis = Prop.xAtYzero
    plKr =Prop("Kr" , r"$k_r$" , "relative permeability",        [0.,1.] ); plKr.icol=2;  plKr.icol2=3
    plKw =Prop("Krw", r"$k_{rw}$",  "water Kr",                  [0.,1.] ); plKw.icol=2
    plKo =Prop("Kro", r"$k_{ro}$",  "oil Kr",                    [0.,1.] ); plKo.icol=3
    plRI =Prop("RI" , r"$RI$",  "resistivity index",          [1.,1000.] ); plRI.icol=4;  plRI.Dx=[0.01,1.]; plRI.small=1.; plRI.ploT.ploT = plt.loglog
    OilR =Prop("OilR","Oil Recovery, FOIP", "oil recovery factor", [0.,1.] ); OilR.grpFunc=grepOilR;  OilR.icycl = 2
    pSgr =Prop("Sgr",  r"$S_{gr}$" , "gas residual saturation",    [0.,0.7] ); pSgr.grpFunc=grepSiSr;  pSgr.icycl = 2;   pSgr.xlbl=r"$S_{gi}$"
    pSor =Prop("Sor",  r"$S_{or}$" , "oil residual saturation",    [0.,0.7] ); pSor.grpFunc=grepSor;   pSor.icycl = 2
    pPhi =Prop("porosity",  r"$\phi$" , "porosity"                          ); pPhi.grpFunc=grepFloatInRes
    pKsp =Prop("permeability",r"$k_{abs}$", r"permeability \(D\)", [0.,1e-6] ); pKsp.grpFunc=grepFloatInRes;  pKsp.unit=9.869233e-13
    pFF  =Prop("formationfactor", r"$FF$" , "formation factor" ,  [0.,1000.]); pFF.grpFunc=grepFloatInRes;   pFF.Dx=[0.01,1.]; pFF.small=1.
    pSwD =Prop("Swi",  r"$S_{wi}$", "initial water saturation" , [0.,1.]); pSwD.grpFunc=grepSwi;   pSwD.icycl = 1
    Amot =Prop("Amot", "Amott index" , "Ammot index" ,            [-1.,1.], "AmottI"); Amot.grpFunc=grepFloatInRes
    pnTg =Prop("pnTg", "Network tag" , "Network" ) # efect of voxel size ...

    Clay =Prop("Clay", "$S_w$ sub-res.", "sub-resolution porosity",[0,1], "AddClay")
    CAdv =Prop("CAdv", "$θ_{adv}$", "advancing contact$~$angle",[0,180], "AlterContAng");  CAdv.valBfor="4 "; CAdv.valAftr=" 0.2 -3.  rand   0."
    CBox =Prop("CBox", "$k_r$ Calc Box", "upscaling bounds",[0.,1.], "UpscaleBox")
    NpIm =Prop("NpIm", "Pressure drop", "pressure difference", [0.,1.], "Cycle2_BC");      NpIm.valBfor="T   F       T   T      DP   "
    pSwi =Prop("Swi",  "$S_{wi}$", "initial water saturation" , [0.,1.], "Cycle1");   pSwi.valAftr= "  1e5   0.025     T   T"
    pPci =Prop("Pci",  "$P_{ci}$", "initial capillary pressure",[0.,1e5], "Cycle1");  pPci.valBfor="0. "; pPci.valAftr = "   0.05     T   T"

    for prp in [plPc,plKr,plKw,plKo,plRI,OilR,pSgr,pSor,pSwD] : prp.kywrd="_SwPcKrwKroRI_cycle"; prp.nSkip = 2;  prp.endKy = "\n\n"



    # snflow calibration, old

    DelPw = Prop("DelPw",r"${\Delta}P_w$", "Water viscous pressure difference", [0,1000], "Cycle2_BC");  DelPw.valBfor="T F  T T  DP "; DelPw.valAftr=" 1"
    DelPo = Prop("DelPo",r"${\Delta}P_o$",   "Oil viscous pressure difference", [0,1000], "Cycle2_BC");  DelPo.valBfor="T F  T T  DP  1 "

    Alfact = Prop("Alfact","Alfact", "Layer area coefficient", [0,2], "Alfact")

    btaKcpl = Prop("btaKcpl","btaKcpl", "cos beta+theta mult factor", [0,1], "btaKcpl"  )

    cTortu = Prop("cTortu","Corner Tortuosity",   "corner Tortuosity coefficient", [0,1] )
    mrgLvl = Prop("mrgLvl","Merge levels 2&3?","merge corner sublevels 2&3?", [0,1])
    cSmotA = Prop("cSmotA","Smooth corners?","Smooth pore-to-throat corner$~$area?", [0,1])
    pSatFr = Prop("pSatFr","layer volume @pore", "pore saturation contribution", [0,1])
    xKcplT = Prop("xKcplT","xKcplT",      "piston-like threshold-$P_c$ scale", [0,1])
    xKcplP = Prop("xKcplP","xKcplP", "pore piston-like threshold-$P_c$ scale", [0,1] )
    nAjCrs = Prop("nAjCrs","Corner connectivity", "corner connectivity number", [0,1],"nAjCrs"  )
    pisKcS = Prop("pisKcS",r"$S_{w,pist}$",       r"$S_w$ piston-like curvature coefficient", [0,1])
    ptEx12 = Prop("ptEx12","ptEx12",   "throat expansion coefficients 1&2", [0,1],"ptExs");  ptEx12.valAftr=" 0"; """ Error wrong after"""
    ptEx23 = Prop("ptEx23","ptEx23",   "throat expansion coefficients 2&3", [0,1],"ptExs");  ptEx23.valBfor="1 "
    crnKGa = Prop("crnKGa",r"$C^{kq}_\gamma$", "conductance corner-angle coefficient", [0,0.1])
    crnKX1 = Prop("crnKX1",r"$C^{kq}_1$",         "conductance coefficient-1", [0,1],"crnKXs" );        crnKX1.valAftr=" 1.5 1"
    crnKX2 = Prop("crnKX2",r"$C^{kq}_2$",         "conductance coefficient-2", [0,1],"crnKXs" );        crnKX2.valBfor="0.05 "; crnKX2.valAftr=" 1"
    crnKX3 = Prop("crnKX3",r"$C^{kq}_3$",         "conductance coefficient-3", [0,1],"crnKXs" );        crnKX3.valBfor="0.05 1.5 "
    sagKcP = Prop("sagKcP",r"$K_{c,sagi}^{pore}$",  "pore sagittal curvature coefficient", [0,5])
    sagKcT = Prop("sagKcT",r"$K_{c,sagi}^{throat}$",r"throat sagittal curvature coefficient", [0,5])

    crKqPis = Prop("crKqPis",r"$C^{kq}_{pist}$", "piston-like conductivity coefficient", [0,1],"crKqPis")
    eKqPist = Prop("eKqPist",r"$F^{kq}_{pist}$", "piston-like conductivity exponent", [0,1],"eKqPist")
    eKqCntr = Prop("eKqCntr",r"$F^{kq}_{cntr}$", "centre-phase conductivity exponent", [0,1],"eKqCntr")

    CArc =Prop("CArc", r"$θ_{rec}$", "receding contact$~$angle", [0,180], "InitContAng");   CArc.valBfor="1 "; CArc.valAftr=" 0.2 -3.   rand   0."
    CAdv =Prop("CAdv", r"$θ_{adv}$", "advancing contact$~$angle", [0,180], "AlterContAng");  CAdv.valBfor="4 "; CAdv.valAftr=" 0.2 -3.  rand   0."
    Clay =Prop("Clay", r"$S_w$ sub-res.", "sub-resolution porosity", [0,1], "AddClay")

    AAow = Prop("AAow","$θ_{frac}$", "fractionally altered contact$~$angle", [0,180],"FracContAng");     AAow.valBfor="4 "; AAow.valAftr=" 0.2 -3.   rand   0."
    AAal = Prop("AAal","$θ_{all}$", "Advancing contact$~$angles", [0,180],"FracContAng");     AAal.valBfor="4 ";   AAal.valAftr=" 0.2 -3.   rand   0." # same as AAow but use for spatially correlated single-wettability distribution
    AAfr = Prop("AAfr","Altered-wet fraction", "altered contact$~$angle fraction", [0,180],"FracContOpt"); AAfr.valAftr=" V   O  corr O    1   3   0.2 -3.    rand"
    AAxC = Prop("AAxC","$θ_{frac}$ cor.len.","wettability spatial correlation", [0,180],"FracContOpt");  AAxC.valBfor="0.7 V   O  corr O  "; AAxC.valAftr="  0.2 -3.    rand"

    FOrC = Prop("FOrC","$θ_{frac}$ R.cor.", "fractional-wettability radius correlation", [0,180],"FracContOpt");   FOrC.valBfor="0.7  V   O  corr O    1   3   0.2 -3. "
    CArC = Prop("CArC","$θ_{adv}$ R.cor.", "contact$~$angle radius correlation", [0,180],"AlterContAng");  CArC.valBfor="-1 TOSET 4  CAmin CAmax 0.2 -3."; CArC.valAftr="  0."
    FRrC = Prop("FRrC","$θ_{adv}$ R.cor.", "contact$~$angle radius correlation", [0,180],"FracContAng");  FRrC.valBfor="-1 TOSET 4  CAmin CAmax 0.2 -3."; FRrC.valAftr="  0."
    def setAllRMaxMinRand(sim, prp, val):  sim.setInpTag(FOrC, val) ;   sim.setInpTag(CArC, val) ;   sim.setInpTag(FRrC, val)  # noqa: ARG001
    FArC = Prop("FArC", "$θ_{adv}$ R.cor.", "contact$~$angle radius correlation", [0,180]); FArC.setFunc = setAllRMaxMinRand

    rufBias = Prop("rufBias","RcRoughBias", "radius shift due to filters", [0,5],"RcRoughBias")
    RcRnd = Prop("RcRnd","maxRcRandness", "uncertainty in inscribed radius", [0,5],"maxRcRandness")
    PcRnd = Prop("PcRnd","maxPcRandness", "relative uncertainty in inscribed radius", [0,5],"maxPcRandness")

    slvTyp = Prop("slvTyp", "solver type", "solver type", [0,5],"Solver");           slvTyp.valAftr=" 1e-18 1e-29  1000  F  F  1e18"
    slvTol = Prop("slvTol", "solver tolerance", "solver tolerance", [0,1],"Solver"); slvTol.valBfor="1 ";  slvTol.valAftr=" 1e-29  1000  F  F  1e18"
    slvCut = Prop("slvCut", "cond. cut-off", "solver cond. cut-off", [0,1],"Solver"); slvCut.valBfor="1  1e-18 "; slvCut.valAftr="  1000  F  F  1e18"
    slvCap = Prop("slvCap", "cond. cap factor","solver cond. cap factor", [0,1],"Solver"); slvCap.valBfor="1  1e-18 1e-29 "; slvCap.valAftr="   F  F  1e18"
    slvScl = Prop("slvScl", "solver scale", "solver scale factor", [0,1],"Solver");      slvScl.valBfor="1  1e-18 1e-29  1000  F  F "
    btaKcpl2 = Prop("btaKcpl2", "btaKcpl2", "cos$~$β+θ coefficient$~$2", [0,1.2])
    btaKcpl  = Prop("btaKcpl", "btaKcpl", "cos$~$β+θ coefficient$~$1", [0,1.2])
    HplCor  = Prop("HplCor", "HplCor", "Throat perimeter correction", [0,1.2]) # @throat
    AplCor  = Prop("AplCor", "AplCor", "Throat area correction", [0,1.2])
    HprCor  = Prop("HprCor", "HprCor", "Pore perimeter correction", [0,1.2]) # @pore
    AprCor  = Prop("AprCor", "AprCor", "Pore area correction", [0,1.2])
except: raise



""" ============= FlowSim ============== """

class FlowSim: # Flow simulation data (Method, image, parameters .series style)
    def __init__(my, tag: str, lgnd: str, img: VoxImg, mtd: Method, styl: Seri, keyVals: dict, forceReRun=False):  # FlowSim()
        my.tag = tag # simulation output suffix
        my.lgnd = toCaption(lgnd) # simulation plots legend,
        my.img = img
        my.mtd = mtd
        my.forceReRun = forceReRun
        my.styl = styl
        my.keyVals = keyVals.copy()
        my.resStrs_ = {} # catch output files
        my.logs_ = ""
        my.simres = {}

    def runSim(my, nam, forceRun=None):
        if forceRun is None:
            forceRun = my.forceReRun

        img=my.img; mtd=my.mtd
        disp(f"\n\n{nam}, FlowSim.{mtd.name}.{mtd.runSim.__name__} from {Path.cwd()}, {my.tag}") # : {my.keyVals}
        ret = mtd.runSim(kwrds=my.keyVals, netnam=img.netname(mtd), resSuffix=my.tag, forceRun=forceRun, netDir=img.netDir, **mtd.simArgs())
        ensure(ret==0, f"Failed: {mtd.name}.{mtd.runSim.__name__} on {img.name}, see {my.logPath()}")
        return ret

    def setInpTag(my, prp: Prop, val):
        if prp.setFunc :
            tag=my.tag
            prp.setFunc(my,prp,val)
            if PatchDEA: my.tag =  tag+prp.name+str(val)
        elif isinstance(val,(list,np.ndarray)): #,pd.core.series.Series
            my.keyVals[prp.kywrd] = f"{prp.valBfor} {' '.join(map(str, val))} {prp.valAftr}"
            my.simres[prp.name] = val
            my.tag +=  prp.name+"".join(map(str, val))
        else:
            my.keyVals[prp.kywrd] = f"{prp.valBfor} {val!s} {prp.valAftr}"
            my.simres[prp.name] = val
            my.tag +=  prp.name+str(val)

    def getRes_(my, prp: Prop, icycl=0):#, pTg=''
        # ky=prp.name+pTg+(str(icycl) if icycl else '')
        ky=prp.name+(str(icycl) if icycl else "")
        if ky in my.simres : return my.simres[ky]
        if icycl: prp.icycl=icycl
        res = prp.grpFunc(my, prp)
        if np.isscalar(res):
            if(res<prp.Dy[0]):
                disp(f"outside bounds, {ky}: {res!s}")
                res=max(res,prp.Dy[0]-0.1*(prp.Dy[1]-prp.Dy[0]))
            if(res>prp.Dy[1]):
                disp(f"outside bounds, {ky}: {res!s}")
                res=min(res,prp.Dy[1]+0.1*(prp.Dy[1]-prp.Dy[0]))
        my.simres[ky] = res
        return res

    def getRes(my, prp: Prop, icycl=0):
        if abs(prp.unit-1)>0.01 and prp.unit>1e-11:  disp(f"{prp.name}.unit: {prp.unit}")
        return my.getRes_(prp,icycl)/prp.unit
    def resName(my):          return my.img.netname(my.mtd)+my.tag
    def resPath(my, prp: Prop=pNon) -> Path: return Path(my.mtd.resPrefix+my.resName()+prp.filExt+ my.mtd.outsfx).absolute()
    def resFile(my, prp: Prop=pNon) -> str:  return str(Path(my.mtd.resPrefix+my.resName()+prp.filExt+ my.mtd.outsfx).absolute())
    def logPath(my) -> Path:          return Path(f"{my.mtd.resPrefix}{my.resName()}_{my.mtd.app}.log").absolute()

    def getLines(my, prp: Prop) -> str:  # read and catch output files as strings
        nam=f"_{prp.filExt}"  # = my.resFile(prp)
        if not my.resStrs_.get(nam):
            with my.resPath(prp).open() as f:
                my.resStrs_[nam] = f.read()
        return my.resStrs_.get(nam)

    def getLogs(my) -> str:
        if not my.logs_:
            with my.logPath().open() as f:
                my.logs_ = f.read()
        return my.logs_




""" ============= Uncertainty ============= """


def mapxys(xy, xref):
    """map xy tabulation to scaled xref, scaled by xy[:,0]s range,
    leading to one-to-one correspondence in the data points"""
    minx1, minx2 = min(xref), min(xy[:,0])
    newx = (xref-minx1)*(max(xy[:,0])-minx2)/(max(xref)-minx1) + minx2
    res=[newx]
    for ii in range(1,len(xy[0])): res.append(np.interp(newx, xy[:,0], xy[:,ii]))
    return np.transpose(np.array(res))


_pI=0 # _pI  to switch start index, between 0 or 1
class UncSim: # Uncertainity quantification using a set of FlowSim, by default tagged by I0,I1...
    nProc=8 ; nSim=8 ; _I_="I" # default   ***UncSim.nProc***, ***UncSim.nSim*** and ***UncSim._I_***
    alpha="80"
    def __init__(my, tag, nSim=8, sims: list[FlowSim]|None = None, tags: list[str]|None = None, **kwargs): # agns0 shall be tag
        if sims is not None:
            my.sims = sims
        elif tags is not None:
            print("UncSim", tag, tags)
            my.sims = [ FlowSim(tag+tg, **kwargs) for tg in tags ]
        else:
            my.sims = [ FlowSim(UncSim._I_+str(ii+_pI)+tag, **kwargs) for ii in range(nSim) ]
        my.tag=tag
        my.img=my.sims[0].img
        my.mtd=my.sims[0].mtd # used in disp
        my.styl=my.sims[0].styl
        my.lgnd=my.sims[0].lgnd
        my.simres={}

    def runSim(my):
        runPar(my.sims,my.nProc)

    def resName(my):    return f"Unc-{my.img.name}{my.tag}"
    def resPath(my, prp=pNon): raise RuntimeError("Unc Sim:res Path")  # noqa: ARG002, EM101
    def logPath(my):          raise RuntimeError("Unc Sim:log Path")  # noqa: EM101

    def setInpTag(my, prp,val):
        for sim in my.sims: sim.setInpTag(prp,val)

    def getRes_(my, prp, icycl=0, varI=""):
        ky=f"{prp.name}{str(icycl) if icycl else ''}_{varI}"
        if ky in my.simres :
            return my.simres[ky]

        ress=[]
        for sim in my.sims:
            ress.append(sim.getRes_(prp, icycl))
        res=ress[0] # by default return first value
        if varI and isinstance(res,(list,np.ndarray)): #,pd.core.series.Series # if kr, pc, RI
            # for rs in ress[1:]:   rs = mapxys(rs, res[:,0]) # resize and map after scaling x
            if   varI=="bgn":  res=ress[0]
            elif varI=="2nd":  res=ress[1]
            elif varI=="end":  res=ress[-1]
            # if   varI=='high':
                # for ii in range(len(ress[0])):   res[ii] = st.max(ress[:][ii])
            # elif varI=='low':
                # for ii in range(len(ress[0])):   res[ii] = st.min(ress[:][ii])
            # elif varI=='sdv': # standard deviation
                # for ii in range(len(ress[0])):   res[ii] = st.pstdev(ress[:][ii])
            # elif varI=='avg': # standard deviation
                # for ii in range(len(ress[0])):   res[ii] = st.mean(ress[:][ii])
            elif varI=="sdv": # standard deviation
                resz=np.array(ress)
                res=st.stdev(resz)  # ; ensure(len(mean)==len(ress[0]))

            else: DbgMsg("bad varI")
                # for ii in range(len(ress[0])):   res[ii] = st.mean(ress[:][ii])
        elif varI:
            if   varI=="max":  res=st.max(ress)
            elif varI=="sdv":  res=st.stdev(ress) #.pstdev(ress)
            else:              res=st.mean(ress)
        my.simres[ky] = res
        return res

    def getRes(my, prp, icycl=0, varI=""):  return my.getRes_(prp, icycl, varI)/prp.unit

    def getLines(my, prp):  raise RuntimeError("Unc Sim:getLines")  # noqa: ARG002, EM101

    def getLogs(my):  raise RuntimeError("Unc Sim:getLogs")  # noqa: EM101

class UncNetSim(UncSim):
    def __init__(my, tag, *args, **kwargs):
        UncSim.__init__(my, tag, *args, **kwargs)
        for ii,sim in enumerate(my.sims):
            sim.mtd=copy.deepcopy(sim.mtd)
            sim.mtd.netsfx=f"I{ii!s}{sim.mtd.netsfx}"  # prepend tag to mtd.netsfx

class Unc3Sim(UncSim):  # Uncertainity using a set of 3 FlowSim s: mean/mid, min and max
    def __init__(my, tag, *args, **kwargs):  UncSim.__init__(my, tag,*args, nSim=3,**kwargs)
