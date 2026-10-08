from __future__ import annotations

# basic python utilities used in testing etc. WARNING: This needs a lot more cleanup!
import functools
import inspect
import os
import re
import shlex
import subprocess
import sys
import sysconfig
from pathlib import Path

######################  SET SCRIPT DIRECTORIES    ######################


def _load_dotenv_parents(start_path: Path, max_levels: int = 5) -> None:
    """Find and load any .env files in start_path or up to max_levels parent directories into os.environ."""
    curr = start_path.resolve()
    if curr.is_file():
        curr = curr.parent
    dirs = [curr]
    for _ in range(max_levels):
        if curr.parent == curr:
            break
        curr = curr.parent
        dirs.append(curr)

    for d in reversed(dirs):
        env_file = d / ".env"
        if env_file.is_file():
            try:
                for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("export "):
                        line = line[len("export ") :].strip()
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if v.startswith("~"):
                            v = os.path.expanduser(v)
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


_load_dotenv_parents(Path(__file__))


def _find_msinst_dir(path):
    """Find the directory holding the compiled xpm/snm binaries (MS_INST/bin or MS_INST/Scripts, MS_INST/lib).

    Supports .env in upper directories, make env, as well as global/venv pip install.
    """
    if "MS_INST" in os.environ and Path(os.environ["MS_INST"]).exists():
        return Path(os.environ["MS_INST"])
    src_pnmkit = Path(path).resolve().parent
    if src_pnmkit.name == "pnmkit" and src_pnmkit.parent.name == "src":
        return src_pnmkit.parent.parent / ".venv"
    return Path(sys.prefix)


def _scripts_dir(base: Path) -> Path:
    """Portable venv/prefix scripts directory: bin/ on POSIX, Scripts/ on Windows.

    This is where `pip install` (e.g. the snm/xpm scikit-build-core wheels)
    places built executables, so it must match exactly.
    """
    if (base / "bin").exists():
        return base / "bin"
    if (base / "Scripts").exists():
        return base / "Scripts"
    return Path(sysconfig.get_path("scripts", vars={"base": str(base), "platbase": str(base)}))


_msInst = _find_msinst_dir(__file__)
_msInstScripts = _scripts_dir(_msInst)

_msInstNote = "Note: MS_INST shall be a checkout's .venv (source/editable install) or sys.prefix (installed package)"
assert _msInstScripts.exists(), f"Error: {_msInstScripts} not found,\n{_msInstNote}"

MS_INST = str(_msInst)

msEnv = os.environ.copy()

# Disable problematic OpenCL/GL components in hwloc to prevent crashes during MPI initialization
if "HWLOC_COMPONENTS" not in msEnv:
    msEnv["HWLOC_COMPONENTS"] = "-opencl,-gl"
if "HWLOC_COMPONENTS" not in os.environ:
    os.environ["HWLOC_COMPONENTS"] = "-opencl,-gl"


def _add_to_path(env, path_to_add, var="PATH"):
    sep = os.pathsep
    if not path_to_add:
        return
    path_str = str(path_to_add)
    current_path = env.get(var, "")
    if path_str not in current_path.split(sep):
        env[var] = path_str + sep + current_path


_add_to_path(msEnv, _msInstScripts)
_add_to_path(os.environ, _msInstScripts)

# Shared-library search path: POSIX uses LD_LIBRARY_PATH, macOS uses
# DYLD_LIBRARY_PATH; Windows resolves DLLs via PATH, so also add "lib" there.
_msInstLib = _msInst / "lib"
if sys.platform == "darwin":
    _add_to_path(msEnv, _msInstLib, var="DYLD_LIBRARY_PATH")
    _add_to_path(os.environ, _msInstLib, var="DYLD_LIBRARY_PATH")
elif os.name == "posix":
    _add_to_path(msEnv, _msInstLib, var="LD_LIBRARY_PATH")
    _add_to_path(os.environ, _msInstLib, var="LD_LIBRARY_PATH")
else:
    _add_to_path(msEnv, _msInstLib)
    _add_to_path(os.environ, _msInstLib)

# Extra fallback for a local (non-pip) build layout, e.g. `make install-snm`.
for _extra_name in ("bin", "Scripts"):
    _extra_bin = Path(__file__).absolute().parent.parent / _extra_name
    _add_to_path(msEnv, _extra_bin)
    _add_to_path(os.environ, _extra_bin)

######################  BASIC TEST UTILITIES  ##########################

disp = functools.partial(print, flush=True)
mkdr = functools.partial(os.makedirs, exist_ok=True)


def dbg_msg(message="", nTrace=4, isError=0, endl="\n", nSkipTrace=1):
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
    dbg_msg(message, nTrace=nTrace + 1, isError=True, nSkipTrace=nSkipTrace + 1)
    if abort:
        sys.exit(abort)


def ensure(okey, message="", abort=0, nTrace=2, nSkipTrace=1):
    if not okey:
        alert(message, abort, None, nTrace + 1, nSkipTrace + 1)


def run_sh(resDir: str, script: str, logfile=None, envs=None):
    """Run a command in resDir."""
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
    argv = shlex.split(script, posix=(os.name != "nt"))
    ret = subprocess.run(argv, stdout=logfile, stderr=logfile, shell=False, cwd=resDir, env=myenv, check=False)
    if ret.returncode != 0:
        msg = f"Error: '{script}' returned {ret.returncode}"
        if oNam:
            msg = f"{msg}, See {oNam}"
        raise RuntimeError(msg)


def grab_scalar(lines="", keyword="Kx=", fnamHint=""):
    try:
        for ele in re.split(":|=| |,|\n|\t|;", lines.split(keyword, 1)[1], maxsplit=20):
            if len(ele):
                try:
                    return float(ele)
                except ValueError:
                    dbg_msg(f"no valid data for {keyword} in {Path.cwd()}/{fnamHint}, got {ele}")
                    return float("NaN")
    except Exception:
        dbg_msg(f"{keyword} not in file (?) {Path.cwd()}/{fnamHint} ", 6)
    return float("NaN")


def read_scalar(inFIle="summary.txt", keyword="Kx="):
    with Path(inFIle).open() as f:
        lines = f.read()
        return grab_scalar(lines, keyword, inFIle)


def read_deviates(inFIle, keyword, val, frac=0.01, delta=1e-32):
    fVal = read_scalar(inFIle, keyword)
    if abs(fVal - val) < frac * abs(val) + delta:
        print(f"{inFIle} -> {keyword}: {fVal!s} ~= {val!s}")
        return 0
    print(f"{inFIle} -> {keyword}: {fVal!s} != {val!s}")
    return 1


def cd(dest):
    """Change current working directory, returning previous directory as a Path."""
    prev = Path.cwd()
    os.chdir(dest)
    return prev
