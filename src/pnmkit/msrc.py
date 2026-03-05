from __future__ import annotations

# basic python utilities used in testing etc. WARNING: This needs a lot more cleanup!
import functools
import inspect
import os
import re
import subprocess
import sys
from pathlib import Path

######################  SET SCRIPT DIRECTORIES    ######################

_msRoot = Path(__file__).absolute().parent.parent.parent  # git root directory

_msInst = _msRoot / "inst" if (_msRoot / "inst/bin").exists() else _msRoot.parent.parent

_msInstNote="Note: msInst shall be inst/ or .venv/, for `make dev` and `make all` respectively"
assert (_msInst / "bin").exists(), f"Error: {_msInst}/bin not found, root: {_msRoot},\n{_msInstNote}"

msInst = str(_msInst)

msEnv = os.environ.copy()

defaultnm="snm" # not really used atm: tag to allow xpm defaults be added / chosen without conflict with snm ones

def _add_to_path(env, path_to_add):
    sep = os.pathsep
    if not path_to_add:
        return
    path_str = str(path_to_add)
    current_path = env.get("PATH", "")
    if path_str not in current_path.split(sep):
        env["PATH"] = path_str + sep + current_path


_add_to_path(msEnv, _msInst / "bin")
_add_to_path(os.environ, _msInst / "bin")

######################  BASIC TEST UTILITIES  ##########################

disp = functools.partial(print, flush=True)
mkdr = functools.partial(os.makedirs, exist_ok=True)


def DbgMsg(message="", nTrace=4, isError=0, endl="\n", nSkipTrace=1):
    """Dodgy print with just enough debugging info"""
    stak = inspect.stack()
    ErTyp = "Error in " if isError else ""
    if nTrace == 0:
        print(f"{ErTyp} {inspect.getframeinfo(stak[nSkipTrace][0]).function},  {message}")
        return -1
    if min(nTrace, len(stak)) < nSkipTrace + 2:
        er = inspect.getframeinfo(stak[nSkipTrace][0])
        print(f'File "{er.filename}", line {er.lineno}, in {er.function}  {message}')
    else:
        for ii in range(min(nTrace, len(stak) - nSkipTrace)):
            er = inspect.getframeinfo(stak[ii + nSkipTrace][0])
            print(f'File "{er.filename}", line {er.lineno}, in {er.function}')
        if nTrace < len(stak) - nSkipTrace:
            er = inspect.getframeinfo(stak[-1][0])
            print(f'File "{er.filename}", line {er.lineno}, in {er.function}')
        disp(message, endl)
    return isError


def alert(message="", abort=0, err=None, nTrace=1, nSkipTrace=1):
    if err:
        disp(message)
        raise Exception(message) from err
    DbgMsg(message, nTrace=nTrace + 1, isError=True, nSkipTrace=nSkipTrace + 1)
    if abort:
        sys.exit(abort)


def ensure(okey, message="", abort=0, nTrace=2, nSkipTrace=1):
    if not okey:
        alert(message, abort, None, nTrace + 1, nSkipTrace + 1)


def runSh(resDir: str, script: str, logfile=None, envs=None):
    """Run a shell script,
    If the script starts with space or len(script[0])<=3 then logfile=sys.stdout,
    else it is a log file with first word in script with .log suffix, printed to stderr in case of error
    """
    if envs is None:
        envs = {}
    assert Path(resDir).exists(), f"error directory {resDir} not present"
    oNam = str(script).replace("[", "").split(" ")[0]
    disp(f">> {script}")
    if not logfile and len(oNam) > 3 and oNam[0].isalnum():
        log_path = Path(resDir) / f"{oNam}.log"
        logfile = log_path.open("wb")
        oNam = str(log_path.absolute())
    else:
        oNam = ""
    myenv = msEnv.copy()
    myenv.update(envs)
    disp(f"Running {script} in {resDir}, envs: {envs or ''} >> {oNam}")
    ret = subprocess.run(script, stdout=logfile, stderr=logfile, shell=True, cwd=resDir, env=myenv, check=False)
    if ret.returncode != 0:
        msg = f"Error: '{script}' returned {ret.returncode}"
        if oNam:
            msg = f"{msg}, See {oNam}"
        raise RuntimeError(msg)


def grepFloatInStr(lines="", keyword="Kx=", fnamHint=""):
    try:
        for ele in re.split(":|=| |,|\n|\t|;", lines.split(keyword, 1)[1], maxsplit=20):
            if len(ele):
                try:
                    return float(ele)
                except ValueError:
                    DbgMsg(f"no valid data for {keyword} in {Path.cwd()}/{fnamHint}, got {ele}")
                    return float("NaN")
    except Exception:
        DbgMsg(f"{keyword} not in file (?) {Path.cwd()}/{fnamHint} ", 6)
    return float("NaN")


def grepFloatInFile(inFIle="summary.txt", keyword="Kx="):
    with  Path(inFIle).open() as f:
        lines = f.read()
        return grepFloatInStr(lines, keyword, inFIle)

def fileFloatDiffersFrom(inFIle, keyword, val, frac=0.01, delta=1e-32):
    fVal = grepFloatInFile(inFIle, keyword)
    if abs(fVal - val) < frac * abs(val) + delta:
        print(f"{inFIle} -> {keyword}: {fVal!s} ~= {val!s}")
        return 0
    print(f"{inFIle} -> {keyword}: {fVal!s} != {val!s}")
    return 1
