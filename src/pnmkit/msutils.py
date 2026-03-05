"""python utilities for running and post-processing network model results"""
from __future__ import annotations

import io
import re
import subprocess
import sys
import threading
from pathlib import Path
from shutil import which

import numpy as np

from .msrc import DbgMsg, alert, disp, ensure, grepFloatInStr, mkdr, msEnv, msInst, runSh

# import logging;  logging.basicConfig(level=logging.DEBUG, format='(%(threadName)-5s) %(message)s',)


def nil_fn(*args, **kwargs):  # noqa: ARG001
    """does nothing, returns 0"""
    return 0

def signif(x, p=3):
    # by Scott Gigante https://stackoverflow.com/questions/18915378/rounding-to-significant-figures-in-numpy/63272943
    if isinstance(x,(list)): x = np.asarray(x)
    x_positive = np.where(np.isfinite(x) & (x != 0), np.abs(x), 10**(p-1))
    mags = 10 ** (p - 1 - np.floor(np.log10(x_positive)))
    return np.round(x * mags) / mags

def signi3(x, p=3):
    rounded =  signif(x,p)
    strs="| "
    for va in rounded: strs= f"{strs}{va}    |   "
    return strs


def grepTableInFile(inFIle="vxlImage_upscal.dat",keyword="_SwPcKrwKroRI_cycle1", endKy=";", skipLines=2):
    """Read rel-perms, a 2d array:with each row representing: Sw,Pc,Krw,Kro,RI;  Obsolete, use grepTableInRes instead"""
    try:
        with Path(inFIle).open() as fil:
            lines = fil.read()
    except Exception:  DbgMsg(f"ls {inFIle} #: no such file"); return np.zeros((1,5))
    len1=lines.find(keyword)
    len2=lines.find(endKy,len1)-1

    if lines[len1] == "%" or lines[len1:len1+1] == "//":  len1=len1+1

    data="\n".join(lines[len1:len2].splitlines()[skipLines:])
    if (data):
        return np.genfromtxt(io.BytesIO(data))
    DbgMsg(f"{keyword} not found in {inFIle}")
    return np.zeros((1,5))

def grepTableInRes(sim,prp,pTg=""):
    # TODO add Y and Z dir sims here
    lines=sim.getLines(prp)
    ky=prp.kywrd+pTg+ (str(prp.icycl) if prp.icycl else "")
    ensure(lines,f"{ky} not in {sim.resName()}",-1)
    len1=lines.find(ky)
    if len1<0 and len(pTg): return []
    len2=lines.find(prp.endKy,len1)

    if lines[len1] == "%" or lines[len1:len1+1] == "//": len1+=1

    data="\t\n".join(lines[len1:len2].splitlines()[prp.nSkip:]) # +'\n make sure relperm data lines end with "\\t\\n" :\n'
    if (data):
        try: vals = np.genfromtxt(io.BytesIO(str.encode(data)))
        except Exception as e: alert(f"no valid data for {prp} in {Path.cwd()}/{sim.resFile()}\n{e!s}",1)
        if len(vals) < 2 : DbgMsg(f"lenTbl: {len(vals)!s}  {sim.tag}")
        return vals
    ensure(data,f"{ky} not found in {Path.cwd()}/{sim.resFile(prp)},  lin123: {len1} {len2} , #lines: {len(lines)}",1)
    return np.zeros((1,5))


def grepSiSr(sims,prp,pTg=""):
    SiSrs=[]
    gnmSPKwoR1=[]
    for sim in sims :
        try :
            gnmSPKwoR1 = grepTableInRes(sim,prp,pTg)
            SiSr = [1.-gnmSPKwoR1[0][0],1.-gnmSPKwoR1[-1][0]]
            SiSrs.append(SiSr)
        except Exception as _:  DbgMsg(f"no valid data for SiSr in {sim.resFile()}")
    return SiSrs


def grepSor(sim,prp):
    try :
        gnmSPKwoR1 = grepTableInRes(sim,prp)
        return 1.-gnmSPKwoR1[-1][0]
    except Exception as _:  DbgMsg(f"no valid data for SiSr in {sim.resFile()}")
    return 0.

def grepSwi(sim,prp,pTg=""): # this is used only if not set in input, todo check
    try :
        gnmSPKwoR1 = grepTableInRes(sim,prp,pTg)
        return gnmSPKwoR1[-1][0]
    except Exception as _: DbgMsg(f"no valid data for Swi{pTg} in {sim.resFile()}", isError=len(pTg))
    return 0.

def grepOilR(sim,prp):
    try :
        gnmSPKwoR1 = grepTableInRes(sim,prp)
        return (gnmSPKwoR1[-1][0]-gnmSPKwoR1[0][0])/max(1.-gnmSPKwoR1[0][0], 1e-6)
    except Exception as _: DbgMsg(f"no valid data for SiSr in {sim.resFile()}", 6)
    return 0.


def grepFloatInRes(sim, prp,pTg=""):
    return grepFloatInStr(sim.getLines(prp),prp.kywrd+pTg, sim.resFile(prp))

def grepFloatsInRes(sims,prp,pTg=""):
    Kabss=[]
    for sim in sims :
        try : Kabss.append(grepFloatInRes(sim,prp,pTg))
        except Exception: Kabss.append(0.)
    return Kabss


def grepFlotInStrList(lines,keyword="Gavg", endKy="\n", skipLines=1, fnamHint=""):
    valF=0.
    try: vals=re.search(f"{keyword}[:= \t]*(.*?){endKy}", lines, re.DOTALL).group(1).split() #? is for non greediness
    except Exception as e: print(e); DbgMsg(f"{Path.cwd()}/{fnamHint}:0:0,  no{keyword}...{endKy}  \n"); return 0.
    try:
        valF = float(vals[skipLines])
    except ValueError:  DbgMsg(f" ValueError @{skipLines}: {valF}, in file:{fnamHint}:0:0")
    except Exception as e:  print(e); DbgMsg(f"cannot grep {keyword}.*{endKy} in {fnamHint}")
    return valF

def grepFlotInResList(sim,prp,pTg=""):  return grepFlotInStrList(sim.getLines(prp),prp.kywrd+pTg,prp.endKy,prp.skipLines,sim.resFile())

def grepFlotInLogList(sim,prp,pTg=""):  return grepFlotInStrList(sim.getLogs(),prp.kywrd+pTg,prp.endKy,prp.nSkip,sim.logFile())


def grepFixedListInFile(length=0, inFIle="vxlImage_upscal.dat", keyword="_SwPcKrwKroRI_cycle1", endKy="[$\n]"):
    valsF = [0.] * length
    try: lines = Path(inFIle).read_text()
    except Exception as e: DbgMsg(f"Cannot open '{Path.cwd()}/{inFIle}' to read keyword '{keyword}': {e}"); raise

    match = re.search(rf"{keyword}[:= \t]*(.*?){endKy}", lines, re.DOTALL)
    if not match:
        DbgMsg(f"Error: Keyword '{keyword}' not found or matched in file:\n{Path.cwd()}/{inFIle}:0:0")
        return valsF

    vals = match.group(1).split()
    for j in range(min(length, len(vals))):
        try:
            valsF[j] = float(vals[j])
        except ValueError:
            valsF[j] = 0.
            DbgMsg(f"ValueError: Could not convert '{vals[j]}' to float in file:{inFIle}:0")

    return valsF



def grepSubKeysInStr(lines="",keyword="cycle 1", midkey="eP4:", endKy="^$"):
    valsF = []
    matchcycl=re.search(f"{keyword}(.*?){endKy}", lines, re.DOTALL)
    if matchcycl :
        match = re.findall(rf".*{re.escape(midkey)}([-+]?\d*\.*\d+e?[-+]?\d*|\d+)", matchcycl.group(1)) # does not match begining of file
        if match:
            for ele in match :
                try:   val = float(ele) ;   valsF.append(val)
                except ValueError:  pass
    if not valsF :
        valsF.append(0.); DbgMsg(f" connot find  keyword {keyword}, midkey: {midkey}, endKy: {endKy}")
    return valsF

def grepSubKeysInFile(inFIle="xxx.dbg",keyword="cycle 1", midkey="eP4:", endKy="^$"):
    try:
        lines = Path(inFIle).read_text()
    except Exception:
        DbgMsg(f"cannot open {inFIle}")
        return [0.]
    return grepSubKeysInStr(lines,keyword,midkey,endKy)

def readFile(inFIle="xxx.dbg"):
    try:
        lines = Path(inFIle).read_text()
    except Exception:
        DbgMsg(f"cannot open {inFIle}")
        return ""
    disp(f"{inFIle} read")
    return lines

def getThroPcSwKr(fileBaseName="XXX:",tindex=0, props=None):
    if props is None:
        props = ["condW"]
    proc=subprocess.Popen([f"ls   {fileBaseName}[0-9]*"], shell=True, stdout=subprocess.PIPE)
    fnams = proc.stdout.read().split()
    PcSwKr=np.zeros((len(props),max(len(fnams),1)))
    for ii, fnam in enumerate(fnams):
        with Path(fnam).open() as fp:
            for CellData in re.findall("[ \t]*?<CellData.*?>(.*?)[ \t]*?</CellData>", fp.read(), re.S):
                for jj, prop in enumerate(props):
                    for TrotDatas in re.findall(f"[ \t]*?<DataArray.*?{prop}.*?>(.*?)[ \t]*?</DataArray>", CellData, re.S):
                        PcSwKr[jj][ii] = float(TrotDatas.split()[tindex])

    #print PcSwKr[2]
    return PcSwKr



def setPNMKeywordVals(kwrds=None,caseInp="",baseInp="", endchar=";", lines=""):
    """Merge  kwrds with baseInp, if provided, and write as caseInp"""
    if kwrds is None:
        kwrds = {}
    lines=lines[:]#copy
    if baseInp:
        try:
            lines = Path(baseInp).read_text()
            lines = re.sub(r"(?m)^//.*\n?","", lines) # delete comment lines to avoid double-newline being end of keyword, https://docs.python.org/2/library/re.html
            lines = re.sub(r"(?m)^%.*\n?","", lines)
            lines = re.sub(r"//.*","", lines)
            lines = re.sub(r"%.*","", lines)
        except FileNotFoundError:
            print(f"{baseInp} not found, continuing with empty base input")
        for (key, val) in kwrds.items():
            if len(key.strip()):
                lines, nsub = re.subn(r"^[ \t]*"+key+"[ :\r\n]+((?!"+endchar+").)*"+endchar, f"{key}  {val} {endchar}", lines, flags=re.M|re.S)
                if not nsub : lines += f"\n\n {key}: {val} {endchar}\n"
                if not re.search(r"^[ \t]*"+key+"[ :\r\n]+((?!"+endchar+").)*"+endchar, lines, flags=re.M|re.S):
                    disp(lines)  ; disp(f"   *** {key}")  ;  sys.exit(-1)
            elif  len(val.strip()): DbgMsg(f"empty keyword {key}:{val} skipped ",1)
    else:
        for (key, val) in kwrds.items():
            if len(key.strip()):
                lines += f" {key}: {val} {endchar}\n"
            elif  len(val.strip()): DbgMsg(f"empty keyword {key}:{val} skipped ",1)
    Path(caseInp).write_text(lines)


def runXNFlow(kwrds: dict, netnam="", resSuffix="", app="scalor", forceRun=False, resDir="./resultsSNM", netDir="../../SKE", **kwargs):
    """use this to also run pnflow/cnflow and scalor"""
    kwrds = kwrds.copy()
    assert len(resDir) > 2
    assert len(netDir) > 2
    kwrds.update(kwargs)
    if resDir[-1]=="/" : resDir = resDir[:-1]
    if netDir[-1]=="/" : netDir = netDir[:-1]
    iNam=netnam+resSuffix
    lognam=f"{resDir}/{iNam}_{app}.log" # use same file for both log and input
    if forceRun or not Path(lognam).is_file():
        mkdr(resDir)
        if "stage1" in kwrds:   kwrds.update({"networkDir":netDir, "TITLE":resSuffix})
        else:
            netBas=f"{netDir}/{netnam}{kwrds.pop('pnTg', '').replace(' ', '')}"
            netf=netBas
            if app == "scalor" and not netf.endswith("_ms.xmf"):
                netf += "_ms.xmf"
            if netnam[-3:]=="Net"        : netf=f"{netBas}.xmf"
            if (netf[0] != "/") and (not Path(f"{resDir}/{netf}").exists()):
                if app[0]=="c" and app[0]=="p" :     kwrds["NETWORK"] = f"F {netf}"
                else: DbgMsg(f"ls {Path.cwd()}/{resDir}/{netf} # does not exist", 0) #exit(-1)
            kwrds["networkFile"] = netf
            kwrds["TITLE"] = iNam
        kwrds["end"] = "of input"
        setPNMKeywordVals(kwrds, lognam, endchar=";", lines=f"//-*- C -*- {app} input follows: \n{{")

        disp(f"Running {app} on {lognam}")
        with Path(lognam).open("ab") as f:  f.write(b"}")  # append: same input and output file
        local_log = f"{iNam}_{app}.log"
        assert which(app, path=msEnv.get("PATH", "")), f"app {app} not found, check msInst: {msInst}"
        proc=subprocess.Popen([app, local_log], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=resDir, env=msEnv, text=True)
        out, err = proc.communicate()
        if proc.returncode != 0:
            disp(f"--- STDOUT: {app} on {local_log} ---")
            disp(out)
            disp(f"--- STDERR: {app} on {local_log} ---")
            disp(err)
            # still write to log for consistency
            with Path(lognam).open("a") as f:
                f.write(out)
                f.write(err)
        else:
             with Path(lognam).open("a") as f:
                f.write(out)
                f.write(err)
        assert proc.returncode == 0  # return proc.returncode
    t=threading.Timer(0.1, disp, args=[f"Skipping {app}, {Path.cwd()}/{lognam} exists."]); t.start(); t.join() # timer is for pretty-printing
    return 0


def runSKE(kwrds=None, bNam="", resSuffix="", app="skelor", forceRun=False, resDir="./SKE", netDir="./", **kwargs):
    if kwrds is None:
        kwrds = {}
    kwrds = kwrds.copy()
    kwrds.update(kwargs)
    if resDir[-1]=="/" : resDir = resDir[:-1] # network dir
    if netDir[-1]=="/" : netDir = netDir[:-1] # image dir
    inam=f"{bNam}{resSuffix}.mhd"
    lognam=f"{resDir}/{bNam}{resSuffix}.log"
    imgnam=f"{netDir}/{bNam}.mhd"
    if forceRun or not Path(lognam).is_file():
        mkdr(resDir)
        with Path(f"{resDir}/{inam}").open("w") as inf:
            inf.write(f"read {imgnam} 1  \n")
            for ky, vl in  kwrds.items():
                inf.write(f"{ky} \t{vl}\n")
            inf.write(f"name: {bNam}{resSuffix} \n")
        with Path(lognam).open("wb") as logfile:
            disp(f"\n\nRunning {app} on {inam}, dir {resDir}, image: {imgnam}")
            subprocess.Popen(["echo","// -*- C -*- runSKE, ls:"], stdout=logfile, cwd=resDir)
            subprocess.Popen(["ls", inam, imgnam], stdout=logfile, cwd=resDir)
            assert which(app, path=msEnv.get("PATH", "")), f"app {app} not found, check msInst: {msInst}"
            proc=subprocess.Popen([app, inam], stdout=logfile, stderr=logfile, cwd=resDir, env=msEnv)
            proc.wait()
            assert proc.returncode == 0
    elif Path(lognam).is_file():
        disp(f"skipping {app} on {inam}, {lognam} exists ")
    return 0


def runSkip(kwrds={}, bNam="", resSuffix="", app="", forceRun=False, resDir="", netDir=""): print("going to lab for Exp!")  # noqa: ARG001, B006

def runCpDNS1f(kwrds=None, bNam="", resSuffix="", app="", forceRun=False, resDir="./DNS", netDir="./", axs=""):
    # bNam == base-name
    if kwrds is None:
        kwrds = {}
    if resDir[-1]!="/": resDir+="/"
    resnam=f"{resDir}{bNam}{resSuffix}{axs}_relPerms.tsv"
    if Path(resnam).is_file() and not forceRun : disp(f"runSKIP: {bNam} {resSuffix} {app} {resDir} {netDir},  {resnam} exists, skipping"); return None
    disp(f"CpDNS1f: {bNam} {resSuffix} {app} {resDir} {netDir} -> {resnam}")

    if len(axs)==0: axs="X"
    sfx    = f"-1-{axs}.txt"
    casdir = f"{bNam}/{bNam}{resSuffix}-1-{axs}"

    # open summary file
    mkdr(resDir)
    readYZ=False  #- EXP:;
    Kabs="Nan";  FF="Nan"
    inFIle=f"{resDir}{netDir}/summary_{bNam}_corners{sfx}" #  DNS,  Note: in netDir, ../ converted to ./

    sumry = None
    with  Path(inFIle).open():
        sumry  = inFIle
    if sumry is None:
        readYZ=True  #- EXP:;
        inFIle=f"{resDir}{netDir}/{bNam}_corners-1-X/summary_{bNam}_corners{sfx}"
        with Path(inFIle).open():
            sumry = inFIle
            casdir=f"{resDir}{netDir}/{bNam}_corners-1-X"
    fnam=f"./{casdir}/summary_{bNam}{resSuffix}{sfx}"
    if sumry is None:
        # fnam='/summary_'+bNam+sfx
        with Path(fnam).open():
            sumry = fnam
        if sumry is None: DbgMsg(f" Neither {Path.cwd()}/{inFIle} nor {fnam} can be read,",1)
    if forceRun and not sumry:
        DbgMsg(f"running DNS {resDir} {netDir}  {Path.cwd()}",1)
        runSh(".", f"AllRunImagePar {bNam} {axs}", envs={"tag":resSuffix})
        # fnam='.'+'/'+casdir+'//summary_'+bNam+sfx
        with Path(fnam).open():
            sumry = fnam
        if sumry is None: DbgMsg(f"\n\n\n nor {Path.cwd()}/{inFIle} nor {fnam} can be read\n\n\n\n",-1)
    DbgMsg(sumry,0)


    siz = grepFixedListInFile(3, f"{casdir}/vxlImage.mhd","DimSize")
    dx  = grepFixedListInFile(3,  f"{casdir}/vxlImage.mhd","ElementSize")
    bbox= grepFixedListInFile(3, sumry,r" /\( ") # bounding box
    scale=1
    if(siz[1]*dx[1]>bbox[1]+1e-12 or siz[2]*dx[2]>bbox[2]+1e-12):
        scale=(bbox[1]*bbox[2])/(siz[1]*dx[1]*siz[2]*dx[2]);    ensure(scale<1 and scale)
        DbgMsg(f"n: {siz!s}   dx:{dx!s}   bx:{bbox!s} ",0)

    ensure(sumry,f" summary file not found for {bNam}",-1)
    # write data for @DNS @Flow Sim
    with Path(sumry).open() as fp:
        lines = fp.read()
        Phi = grepFloatInStr(lines,"effPorosity=", sumry)*scale
        Kabs = grepFloatInStr(lines,f"K_{axs.lower()}=", sumry)*scale
        FF = grepFloatInStr(lines,f"FF_{axs.lower()}=", sumry)/scale
        try:
            Path(resnam).write_text(f"\n{bNam}_porosity: \t{Phi!s} ;\n{bNam}_permeability: \t{Kabs!s} ;\n{bNam}_formationfactor: \t{FF!s} ;")
        except Exception:
            DbgMsg(f"\n\n\n{resnam} cannot be opened for write\n\n\n\n")
            return None


    if readYZ: #- EXP_1:
        try:
            lines = Path(f"summaries/summary_{bNam}-1-Y.txt").read_text()
            Kabs = grepFloatInStr(lines,"K_y=", inFIle)
            FF = grepFloatInStr(lines,"FF_y=", inFIle)
            Path(f"{resDir}/{bNam}{resSuffix}Y_relPerms.tsv").write_text(
                f"\n{bNam}_porosity: \t{Phi!s} ;\n{bNam}_permeability: \t{Kabs!s} ;\n{bNam}_formationfactor: \t{FF!s} ;"
            )
        except Exception:  pass
        try:
            lines = Path(f"summaries/summary_{bNam}-1-Z.txt").read_text()
            Kabs = grepFloatInStr(lines,"K_z=", inFIle)
            FF = grepFloatInStr(lines,"FF_z=", inFIle)
            Path(f"{resDir}/{bNam}{resSuffix}Z_relPerms.tsv").write_text(
                f"\n{bNam}_porosity: \t{Phi!s} ;\n{bNam}_permeability: \t{Kabs!s} ;\n{bNam}_formationfactor: \t{FF!s} ;"
            )
        except Exception:  pass #- EXP_1;
    return 0



def runLog(sma, _tlok, runSim):
    with sma: runSim(threading.currentThread().getName())   # with tlok:  disp('Running: '+ name)
def runPar(sims,nProc):  #=[],4
    disp(f"runPar{{ running {len(sims)} simulations using {nProc} threads, mtd: {sims[0].mtd.mNam}")
    sma = threading.Semaphore(nProc)
    tlok = threading.Lock()
    thrds=[]
    for ii,sim in enumerate(sims):
        t = threading.Thread(target=runLog, name=f"Trd{ii!s} {sim.resName()}", args=(sma, tlok, sim.runSim))
        t.start()
        thrds.append(t)
    for trd in thrds: trd.join()
    disp("} ")
