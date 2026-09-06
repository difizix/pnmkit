"""python utilities for running and post-processing network model results"""

from __future__ import annotations

import glob
import io
import re
import subprocess
import sys
import threading
from pathlib import Path
from shutil import which

import numpy as np

from .runtime import alert, dbg_msg, disp, ensure, grab_scalar, mkdr, msEnv, msInst, run_sh

# import logging;  logging.basicConfig(level=logging.DEBUG, format='(%(threadName)-5s) %(message)s',)


def nil_fn(*args, **kwargs):  # noqa: ARG001
    """does nothing, returns 0"""
    return 0


def read_table(inFIle="vxlImage_upscal.dat", keyword="_SwPcKrwKroRI_cycle1", endKy=";", skipLines=2):
    """Read rel-perms, a 2d array:with each row representing: Sw,Pc,Krw,Kro,RI;  Obsolete, use get_table instead"""
    try:
        with Path(inFIle).open() as fil:
            lines = fil.read()
    except Exception:
        dbg_msg(f"ls {inFIle} #: no such file")
        return np.zeros((1, 5))
    len1 = lines.find(keyword)
    len2 = lines.find(endKy, len1) - 1

    if lines[len1] == "%" or lines[len1 : len1 + 1] == "//":
        len1 = len1 + 1

    data = "\n".join(lines[len1:len2].splitlines()[skipLines:])
    if data:
        return np.genfromtxt(io.BytesIO(data))
    dbg_msg(f"{keyword} not found in {inFIle}")
    return np.zeros((1, 5))


# TODO move anything with sim to models.py, to avoid circular dependancy


def get_table(sim, prp, pTg=""):
    # TODO add Y and Z dir sims here
    lines = sim.getLines(prp)
    ky = prp.kywrd + pTg + (str(prp.icycle) if prp.icycle else "")
    ensure(lines, f"{ky} not in {sim.resName()}", -1)
    len1 = lines.find(ky)
    if len1 < 0 and len(pTg):
        return []
    len2 = lines.find(prp.endKy, len1)

    if lines[len1] == "%" or lines[len1 : len1 + 1] == "//":
        len1 += 1

    data = "\t\n".join(lines[len1:len2].splitlines()[prp.nSkip :])
    if data:
        try:
            vals = np.genfromtxt(io.BytesIO(str.encode(data)))
        except Exception as e:
            alert(f"no valid data for {prp} in {sim.resFile()}\n{e!s}", 1)
        if len(vals) < 2:
            dbg_msg(f"lenTbl: {len(vals)!s}  {sim.tag}")
        return vals
    ensure(data, f"{ky} not found in {sim.resFile(prp)},  lin123: {len1} {len2} , #lines: {len(lines)}", 1)
    return np.zeros((1, 5))


def get_si_sr(sims, prp, pTg=""):
    SiSrs = []
    SPKwoR1 = []
    for sim in sims:
        try:
            SPKwoR1 = get_table(sim, prp, pTg)
            SiSr = [1.0 - SPKwoR1[0][0], 1.0 - SPKwoR1[-1][0]]
            SiSrs.append(SiSr)
        except Exception as _:
            dbg_msg(f"no valid data for SiSr in {sim.resFile()}")
    return SiSrs


def get_sor(sim, prp):
    try:
        SPKwoR1 = get_table(sim, prp)
        return 1.0 - SPKwoR1[-1][0]
    except Exception as _:
        dbg_msg(f"no valid data for SiSr in {sim.resFile()}")
    return 0.0


def grep_swi(sim, prp, pTg=""):  # this is used only if not set in input, todo check
    try:
        SPKwoR1 = get_table(sim, prp, pTg)
        return SPKwoR1[0][0]
    except Exception as _:
        dbg_msg(f"no valid data for Swi{pTg} in {sim.resFile()}", isError=len(pTg))
    return 0.0


def get_oil_r(sim, prp):
    try:
        SPKwoR1 = get_table(sim, prp)
        return (SPKwoR1[-1][0] - SPKwoR1[0][0]) / max(1.0 - SPKwoR1[0][0], 1e-6)
    except Exception as _:
        dbg_msg(f"no valid data for SiSr in {sim.resFile()}", 6)
    return 0.0


def get_scalar(sim, prp, pTg=""):
    nSkip = getattr(prp, "nSkip", 0)
    assert nSkip == 0, "fixme, replace get_scalar with get_array"
    return grab_scalar(sim.getLines(prp), prp.kywrd + pTg, sim.resFile(prp))


def grab_array(length: int, lines: str = "", keyword: str = "", endKy: str = r"[$\n]", skip: int = 0, fnamHint: str = "") -> list[float]:
    """Extract a fixed-length array of floats from string `lines`."""
    valsF = [0.0] * length
    if not lines:
        return valsF
    if keyword:
        match = re.search(rf"{keyword}[:= \t]*(.*?){endKy}", lines, re.DOTALL)
        if not match:
            dbg_msg(f"Error: Keyword '{keyword}' not found in {Path.cwd()}/{fnamHint}:0:0")
            return valsF
        text = match.group(1)
    else:
        text = lines

    vals = text.split()[skip:]
    for j in range(min(length, len(vals))):
        try:
            valsF[j] = float(vals[j])
        except ValueError:
            valsF[j] = 0.0
            dbg_msg(f"ValueError: Could not convert '{vals[j]}' to float in {fnamHint or 'lines'}")
    return valsF


def read_array(length: int, inFIle: str | Path, keyword: str = "_SwPcKrwKroRI_cycle1", endKy: str = r"[$\n]", skip: int = 0) -> list[float]:
    """Read a file and extract a fixed-length array of floats."""
    try:
        lines = Path(inFIle).read_text()
    except Exception as e:
        dbg_msg(f"Cannot open '{Path.cwd()}/{inFIle}' to read keyword '{keyword}': {e}")
        raise
    return grab_array(length, lines, keyword=keyword, endKy=endKy, skip=skip, fnamHint=str(inFIle))


def grab_list(lines: str = "", keyword: str = "", endKy: str = r"[;\n]", skip: int = 0, fnamHint: str = "") -> list[float]:
    """Extract a variable-length list of floats from string `lines`."""
    if not lines:
        return []
    if keyword:
        match = re.search(rf"{keyword}[:= \t]*(.*?){endKy}", lines, re.DOTALL)
        if not match:
            dbg_msg(f"Error: Keyword '{keyword}' not found in {Path.cwd()}/{fnamHint}:0:0")
            return []
        text = match.group(1)
    else:
        text = lines

    vals = text.split()[skip:]
    res: list[float] = []
    for val in vals:
        try:
            res.append(float(val))
        except ValueError:
            break
    return res


def read_list(inFIle: str | Path, keyword: str = "", endKy: str = r"[;\n]", skip: int = 0) -> list[float]:
    """Read a file and extract a variable-length list of floats."""
    try:
        lines = Path(inFIle).read_text()
    except Exception as e:
        dbg_msg(f"Cannot open '{Path.cwd()}/{inFIle}' to read keyword '{keyword}': {e}")
        raise
    return grab_list(lines, keyword=keyword, endKy=endKy, skip=skip, fnamHint=str(inFIle))


def grab_scalar_sub(lines="", keyword="cycle 1", midkey="eP4:", endKy="^$"):
    valsF = []
    matchcycl = re.search(f"{keyword}(.*?){endKy}", lines, re.DOTALL)
    if matchcycl:
        match = re.findall(rf"{re.escape(midkey)}\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?|\d+)", matchcycl.group(1))
        if match:
            for ele in match:
                try:
                    val = float(ele)
                    valsF.append(val)
                except ValueError:
                    pass
    if not valsF:
        valsF.append(0.0)
        dbg_msg(f" connot find  keyword {keyword}, midkey: {midkey}, endKy: {endKy}")
    return valsF


def read_file(inFIle="xxx.dbg"):
    try:
        lines = Path(inFIle).read_text()
    except Exception:
        dbg_msg(f"cannot open {inFIle}")
        return ""
    disp(f"{inFIle} read")
    return lines


def get_thro_pc_sw_kr(fileBaseName="XXX:", tindex=0, props=None):
    if props is None:
        props = ["condW"]
    fnams = sorted(glob.glob(f"{fileBaseName}[0-9]*"))
    PcSwKr = np.zeros((len(props), max(len(fnams), 1)))
    for ii, fnam in enumerate(fnams):
        with Path(fnam).open() as fp:
            for CellData in re.findall("[ \\t]*?<CellData.*?>(.*?)[ \\t]*?</CellData>", fp.read(), re.DOTALL):
                for jj, prop in enumerate(props):
                    for TrotDatas in re.findall(f"[ \\t]*?<DataArray.*?{prop}.*?>(.*?)[ \\t]*?</DataArray>", CellData, re.DOTALL):
                        PcSwKr[jj][ii] = float(TrotDatas.split()[tindex])

    # print PcSwKr[2]
    return PcSwKr


def write_pnm_input(kwrds=None, caseInp="", baseInp="", endchar=";", lines=""):
    """Merge  kwrds with baseInp, if provided, and write as caseInp"""
    if kwrds is None:
        kwrds = {}
    lines = lines[:]  # copy
    if baseInp:
        try:
            lines = Path(baseInp).read_text()
            lines = re.sub(
                r"(?m)^//.*\n?", "", lines
            )  # delete comment lines to avoid double-newline being end of keyword, https://docs.python.org/2/library/re.html
            lines = re.sub(r"(?m)^%.*\n?", "", lines)
            lines = re.sub(r"//.*", "", lines)
            lines = re.sub(r"%.*", "", lines)
        except FileNotFoundError:
            print(f"{baseInp} not found, continuing with empty base input")
        for key, val in kwrds.items():
            if len(key.strip()):
                lines, nsub = re.subn(
                    r"^[ \t]*" + key + "[ :\r\n]+((?!" + endchar + ").)*" + endchar, f"{key}  {val} {endchar}", lines, flags=re.MULTILINE | re.DOTALL
                )
                if not nsub:
                    lines += f"\n\n {key}: {val} {endchar}\n"
                if not re.search(r"^[ \t]*" + key + "[ :\r\n]+((?!" + endchar + ").)*" + endchar, lines, flags=re.MULTILINE | re.DOTALL):
                    disp(lines)
                    disp(f"   *** {key}")
                    sys.exit(-1)
            elif len(val.strip()):
                dbg_msg(f"empty keyword {key}:{val} skipped ", 1)
    else:
        for key, val in kwrds.items():
            if len(key.strip()):
                lines += f" {key}: {val} {endchar}\n"
            elif len(val.strip()):
                dbg_msg(f"empty keyword {key}:{val} skipped ", 1)
    Path(caseInp).write_text(lines)


def run_xnflow(kwrds: dict, netnam="", resSuffix="", app="scalor", forceRun=False, resDir="./resultsSNM", netDir="../../SKE", **kwargs):
    """use this to also run pnflow/cnflow and scalor"""
    kwrds = kwrds.copy()
    extra_env = kwrds.pop("extra_env", None) or kwargs.pop("extra_env", None)
    resDir = str(Path(resDir).absolute())
    netDir = str(Path(netDir).absolute())
    assert len(resDir) > 2
    assert len(netDir) > 2
    kwrds.update(kwargs)
    if resDir[-1] == "/":
        resDir = resDir[:-1]
    if netDir[-1] == "/":
        netDir = netDir[:-1]
    iNam = kwrds.get("OutputName", netnam + resSuffix)
    lognam = f"{resDir}/{iNam}_{app}.log"  # use same file for both log and input
    if forceRun or not Path(lognam).is_file():
        if forceRun:
            kwrds.setdefault("overwrite", "true")
        mkdr(resDir)
        if "stage1" in kwrds:
            kwrds.update({"NetworkDir": netDir, "OutputName": resSuffix})
        else:
            if kwrds.get("NetworkFile"):
                netf = kwrds["NetworkFile"]
            else:
                netBas = f"{netDir}/{netnam}{kwrds.pop('pnTg', '').replace(' ', '')}"
                netf = netBas
                if app == "scalor" and not netf.endswith("_ms.xmf"):
                    netf += "_ms.xmf"
                if netnam[-3:] == "Net":
                    netf = f"{netBas}.xmf"
            if app == "pnflow":
                netBas = kwrds.pop("NETWORK", "").replace("F ", "").strip()
                if not netBas:
                    netBas = Path(netf).stem
                    for sfx in ("_link1", "_node1", "_ms", "_pn"):
                        netBas = netBas.removesuffix(sfx)
                kwrds.pop("NetworkFile", None)
                kwrds["NETWORK"] = f"F {netBas}"
            elif "NetworkFile" in kwrds or "NETWORK" not in kwrds:
                kwrds["NetworkFile"] = netf
            kwrds["OutputName"] = iNam
        kwrds["end"] = "of input"
        write_pnm_input(kwrds, lognam, endchar=";", lines=f"//-*- C -*- {app} input follows: \n{{")

        disp(f"Running {app} on {lognam}")
        with Path(lognam).open("ab") as f:
            f.write(b"}")  # append: same input and output file
        local_log = f"{iNam}_{app}.log"
        assert which(app, path=msEnv.get("PATH", "")), f"app {app} not found, check msInst: {msInst}"
        env = msEnv.copy()
        if extra_env is not None:
            env.update(extra_env)
        proc = subprocess.Popen([app, local_log], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=resDir, env=env, text=True)
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
    t = threading.Timer(0.1, disp, args=[f"Skipping {app}, {Path(lognam).absolute()} exists."])
    t.start()
    t.join()  # timer is for pretty-printing
    return 0


def run_ske(kwrds=None, bNam="", resSuffix="", app="skelor", forceRun=False, resDir="./SKE", netDir="./", **kwargs):
    if kwrds is None:
        kwrds = {}
    kwrds = kwrds.copy()
    kwrds.update(kwargs)
    extra_env = kwrds.pop("extra_env", None) or kwargs.pop("extra_env", None)
    if resDir[-1] == "/":
        resDir = resDir[:-1]  # network dir
    if netDir[-1] == "/":
        netDir = netDir[:-1]  # image dir
    inam = f"{bNam}{resSuffix}.mhd"
    lognam = f"{resDir}/{bNam}{resSuffix}.log"
    imgnam = f"{netDir}/{bNam}.mhd"
    if forceRun or not Path(lognam).is_file():
        mkdr(resDir)
        header_content = ""
        if Path(imgnam).is_file():
            try:
                original_content = Path(imgnam).read_text()
                mhd_lines = []
                for line in original_content.splitlines():
                    if any(
                        line.strip().startswith(k)
                        for k in (
                            "ObjectType",
                            "NDims",
                            "ElementType",
                            "ElementByteOrderMSB",
                            "ElementNumberOfChannels",
                            "CompressedData",
                            "DimSize",
                            "ElementSize",
                            "Offset",
                            "ElementDataFile",
                            "Unit",
                            "HeaderSize",
                        )
                    ):
                        mhd_lines.append(line)
                header_content = "\n".join(mhd_lines) + "\n\n"
            except Exception as e:
                disp(f"Warning: could not read original header {imgnam}: {e}")
        with Path(f"{resDir}/{inam}").open("w") as inf:
            inf.write(header_content)
            inf.write(f"filename: {imgnam}\n")
            inf.write(f"read {imgnam} 1  \n")
            out_name = kwrds.pop("OutputName", f"{bNam}{resSuffix}")
            inf.writelines(f"{ky} \t{vl}\n" for ky, vl in kwrds.items())
            inf.write(f"OutputName: {out_name} \n")
        with Path(lognam).open("wb") as logfile:
            disp(f"\n\nRunning {app} on {inam}, dir {resDir}, image: {imgnam}")
            # Was `echo` + `ls` via subprocess (POSIX-only); write the same
            # marker/file-listing lines directly instead, portable everywhere.
            logfile.write(b"// -*- C -*- run_ske, ls:\n")
            logfile.write(f"{inam}\n{imgnam}\n".encode())
            logfile.flush()
            assert which(app, path=msEnv.get("PATH", "")), f"app {app} not found, check msInst: {msInst}"
            env = msEnv.copy()
            if extra_env is not None:
                env.update(extra_env)
            proc = subprocess.Popen([app, inam], stdout=logfile, stderr=logfile, cwd=resDir, env=env)
            proc.wait()
            assert proc.returncode == 0
    elif Path(lognam).is_file():
        disp(f"skipping {app} on {inam}, {lognam} exists ")
    return 0


def run_skip(kwrds={}, bNam="", resSuffix="", app="", forceRun=False, resDir="", netDir=""):  # noqa: ARG001 (args kept for Method.runSim interface parity)
    print("going to lab for Exp!")


def run_cp_dns1f(kwrds=None, bNam="", resSuffix="", app="", forceRun=False, resDir="./DNS", netDir="./", axs=""):
    # bNam == base-name
    if kwrds is None:
        kwrds = {}
    if resDir[-1] != "/":
        resDir += "/"
    resnam = f"{resDir}{bNam}{resSuffix}{axs}_relPerms.tsv"
    if Path(resnam).is_file() and not forceRun:
        disp(f"runSKIP: {bNam} {resSuffix} {app} {resDir} {netDir},  {resnam} exists, skipping")
        return None
    disp(f"CpDNS1f: {bNam} {resSuffix} {app} {resDir} {netDir} -> {resnam}")

    if len(axs) == 0:
        axs = "X"
    sfx = f"-1-{axs}.txt"
    casdir = f"{bNam}/{bNam}{resSuffix}-1-{axs}"

    # open summary file
    mkdr(resDir)
    readYZ = False  # - EXP:;
    Kabs = "Nan"
    FF = "Nan"
    inFIle = f"{resDir}{netDir}/summary_{bNam}_corners{sfx}"  #  DNS,  Note: in netDir, ../ converted to ./

    sumry = None
    with Path(inFIle).open():
        sumry = inFIle
    if sumry is None:
        readYZ = True  # - EXP:;
        inFIle = f"{resDir}{netDir}/{bNam}_corners-1-X/summary_{bNam}_corners{sfx}"
        with Path(inFIle).open():
            sumry = inFIle
            casdir = f"{resDir}{netDir}/{bNam}_corners-1-X"
    fnam = f"./{casdir}/summary_{bNam}{resSuffix}{sfx}"
    if sumry is None:
        # fnam='/summary_'+bNam+sfx
        with Path(fnam).open():
            sumry = fnam
        if sumry is None:
            dbg_msg(f" Neither {Path.cwd()}/{inFIle} nor {fnam} can be read,", 1)
    if forceRun and not sumry:
        dbg_msg(f"running DNS {resDir} {netDir}  {Path.cwd()}", 1)
        run_sh(".", f"AllRunImagePar {bNam} {axs}", envs={"tag": resSuffix})
        # fnam='.'+'/'+casdir+'//summary_'+bNam+sfx
        with Path(fnam).open():
            sumry = fnam
        if sumry is None:
            dbg_msg(f"\n\n\n nor {Path.cwd()}/{inFIle} nor {fnam} can be read\n\n\n\n", -1)
    dbg_msg(sumry, 0)

    siz = read_array(3, f"{casdir}/vxlImage.mhd", "DimSize")
    dx = read_array(3, f"{casdir}/vxlImage.mhd", "ElementSize")
    bbox = read_array(3, sumry, r" /\( ")  # bounding box
    scale = 1
    if siz[1] * dx[1] > bbox[1] + 1e-12 or siz[2] * dx[2] > bbox[2] + 1e-12:
        scale = (bbox[1] * bbox[2]) / (siz[1] * dx[1] * siz[2] * dx[2])
        ensure(scale < 1 and scale)
        dbg_msg(f"n: {siz!s}   dx:{dx!s}   bx:{bbox!s} ", 0)

    ensure(sumry, f" summary file not found for {bNam}", -1)
    # write data for @DNS @Flow Sim
    with Path(sumry).open() as fp:
        lines = fp.read()
        Phi = grab_scalar(lines, "effPorosity=", sumry) * scale
        Kabs = grab_scalar(lines, f"K_{axs.lower()}=", sumry) * scale
        FF = grab_scalar(lines, f"FF_{axs.lower()}=", sumry) / scale
        try:
            Path(resnam).write_text(f"\n{bNam}_porosity: \t{Phi!s} ;\n{bNam}_permeability: \t{Kabs!s} ;\n{bNam}_formationfactor: \t{FF!s} ;")
        except Exception:
            dbg_msg(f"\n\n\n{resnam} cannot be opened for write\n\n\n\n")
            return None

    if readYZ:  # - EXP_1:
        try:
            lines = Path(f"summaries/summary_{bNam}-1-Y.txt").read_text()
            Kabs = grab_scalar(lines, "K_y=", inFIle)
            FF = grab_scalar(lines, "FF_y=", inFIle)
            Path(f"{resDir}/{bNam}{resSuffix}Y_relPerms.tsv").write_text(
                f"\n{bNam}_porosity: \t{Phi!s} ;\n{bNam}_permeability: \t{Kabs!s} ;\n{bNam}_formationfactor: \t{FF!s} ;"
            )
        except Exception:
            pass
        try:
            lines = Path(f"summaries/summary_{bNam}-1-Z.txt").read_text()
            Kabs = grab_scalar(lines, "K_z=", inFIle)
            FF = grab_scalar(lines, "FF_z=", inFIle)
            Path(f"{resDir}/{bNam}{resSuffix}Z_relPerms.tsv").write_text(
                f"\n{bNam}_porosity: \t{Phi!s} ;\n{bNam}_permeability: \t{Kabs!s} ;\n{bNam}_formationfactor: \t{FF!s} ;"
            )
        except Exception:
            pass  # - EXP_1;
    return 0


def run_log(sma, _tlok, runSim):
    with sma:
        runSim(threading.currentThread().getName())  # with tlok:  disp('Running: '+ name)


def run_par(sims, nProc):  # =[],4
    disp(f"run_par{{ running {len(sims)} simulations using {nProc} threads, mtd: {sims[0].mtd.mNam}")
    sma = threading.Semaphore(nProc)
    tlok = threading.Lock()
    thrds = []
    for ii, sim in enumerate(sims):
        t = threading.Thread(target=run_log, name=f"Trd{ii!s} {sim.resName()}", args=(sma, tlok, sim.runSim))
        t.start()
        thrds.append(t)
    for trd in thrds:
        trd.join()
    disp("} ")
