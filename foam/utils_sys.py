#!/usr/bin/env python

import glob
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# from multiprocessing import Process
from threading import Thread  # not concurrent!?
from typing import Callable


class TaskMonitor:
    """A singleton that starts a logging loop.

    The logs are written to callback function `shout` that shall be passed to the constructor.
    `shout` should take an `str` as argument.
    It is using thread, so not in parallel to calling thread (!?) TODO explore more!

    Static attributes:
        report_interval_ini (float): initial wait period between logs.
        report_interval_max (float): The wait period increases toward this by a factor of 1.2 (hard-coded!).

    Attributes:
        done (bool): set this true to indicate that the reporting loop shall end as soon as possible!

    """

    # Adjustable parameters
    report_interval_ini = 1.0
    report_interval_max = 300.0

    def __init__(self, shout: Callable[[str], None]):
        self.done = False
        self.shout = shout
        self._process = Thread(target=self._monitor_logs_procs)
        self._process.daemon = True
        self._process.start()

    def _run_ignore_process(self, command: list[str]):
        f = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return f.stdout.decode("utf-8")

    def _monitor_logs_procs(self) -> None:
        """Monitor top processes and newest file and periodically report to log_state:
        1. top running processes of the current user
        2. tail of newest log file in current directory or in any first-level subdirectory
        """
        oldTail = ""
        noWrite = " no new logs detected !!!\n"
        dtSleep = TaskMonitor.report_interval_ini
        start = time.time()

        for _ in range(1000):  # run for a sufficiently long time but not forever
            if self.done:
                return
            prev = time.time()
            # TODO use psutils instead? see https://stackoverflow.com/a/73728794
            ret = self._run_ignore_process(["top", "-n", "1", "-b", "-u", str(os.getuid())])
            out = "\n".join(ret.split(os.linesep)[:16]) + "\n\n"

            # Look for up to one subdir only, to avoid performance issues
            newest = max(glob.glob("*/*") + glob.glob("*"), key=os.path.getctime)
            if "log." in newest or ".log" in newest:
                out += f"tail of {newest}:"
                ret = self._run_ignore_process(["tail", "-n", "20", newest])
                if ret == oldTail:
                    out += noWrite
                else:
                    out += f"\n{ret}\n"
                    oldTail = ret
            elif newest == oldTail:
                out += noWrite
            else:
                out += "Newest modified path is " + newest + "\n"
                oldTail = newest
            now = time.time()
            out += f"\nAt {now - start:.2f}s, monitor took {now - prev:.2f}s, next in {dtSleep:.2f}s\n"

            if self.done:
                return

            self._log2ui(out)

            time.sleep(dtSleep)
            dtSleep = min(dtSleep * 1.2, TaskMonitor.report_interval_max)


def run_shell(command: str, cwd=".") -> None:
    """Run a process and merge stderr into stout
    Arguments:
        command: shell command to run
        cwd: working directory
    Raises:
        subprocess.CalledProcessError
    """

    print("Running", command, flush=True)
    ret = subprocess.run(command, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(ret.stdout.decode(), "\n", flush=True)
    ret.check_returncode()  # raise if error code is non-zero


def run_shell_monitor(command: str, shout: Callable[[str], None], cwd=".") -> None:
    """Run a time-consuming script and periodically calls the monitor function
    Arguments:
        command: main shell command to run
        monitor: where system stateHome
    """

    # Launch two concurrent processes, main job and a task monitor
    tred = TaskMonitor(shout)

    print("Running:", command, flush=True)
    proc = subprocess.Popen(command, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    print(proc.stdout.read().decode(), "\n", flush=True)

    tred.done = True  # still running, but will be terminated by next iteration, or by daemon termination

    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, proc.args)  # same Exception as in subprocess.run()


def test_shMonitor():
    """
    This is not really a test atm!
     TODO:
        1. check total time passed and that the last modified file is reported correctly,
           and that its tail is reported only once
        2. CPU usage results should be checked based on number of lines...
        3. this test if stopped midway/fail will leave trash behind! add try-finally blocks
    """
    pth = Path("test_folder_tmp-")
    pth.mkdir(exist_ok=True)
    command = f"/bin/bash -c 'for i in 1@ 2@ 3@ 4@ 5@; do stdbuf -oL echo $i >> {pth}/log.echo && sleep 2; done'"
    sys.stdout.flush()
    run_shell_monitor(command, lambda msg: print(msg, flush=True))
    sys.stdout.flush()

    with open("log.test_file_tmp-", "bw") as f:
        f.write(b"some text")

    print("\n\n------------\n\n", flush=True)

    time.sleep(10)
    run_shell(command)

    shutil.rmtree(pth)
    Path("log.test_file_tmp-").unlink()
    shutil.disk_usage(".")


if __name__ == "__main__":
    test_shMonitor()
