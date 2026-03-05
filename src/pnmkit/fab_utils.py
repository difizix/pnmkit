from __future__ import annotations

import argparse
import sys
import time
from contextlib import chdir
from pathlib import Path

from fabric import Connection
from invoke import Context
from patchwork.files import exists
from patchwork.transfers import rsync


def get_cpu_load(ctx):
    """Calculates CPU usage percentage using top in batch mode."""
    cmd = "top -bn2 -d 0.5 | grep '%Cpu' | tail -1 | awk '{print 100 - $8}'"
    try:
        return float(ctx.run(cmd, hide=True).stdout.strip())
    except Exception:
        return 100.0


def run_cached_fab(argv):
    parser = argparse.ArgumentParser(description="DiFiziX Modern Remote Runner")
    parser.add_argument("-H", "--host", help="SSH host. If omitted, runs locally.")
    parser.add_argument("-w", "--work-dir", default="sim_run", help="Working directory")
    parser.add_argument("-l", "--log-file", default="cache.log", help="Output/Cache file")
    parser.add_argument("--cpu-limit", type=float, default=50.0)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("cmd", help="Command to run")
    args = parser.parse_args(argv)

    # 1. Initialize Context & Paths
    ctx = Connection(host=args.host) if args.host else Context()
    is_remote = isinstance(ctx, Connection)
    work_path = Path(args.work_dir)

    # 2. Sync / Setup Directory
    if is_remote:
        ctx.run(f"mkdir -p {work_path}")
        print(f"[*] Syncing to remote: {work_path}")
        rsync(ctx, source="./", target=str(work_path), exclude=[".git", "*.log", "__pycache__"])
    else:
        work_path.mkdir(parents=True, exist_ok=True)

    # 3. CPU Load Retry Loop
    for i in range(args.retries):
        load = get_cpu_load(ctx)
        if load <= args.cpu_limit:
            break
        print(f"[!] CPU load {load}% > {args.cpu_limit}%. Retry {i+1}/{args.retries}...")
        time.sleep(10)
    else:
        print("[X] Load threshold exceeded. Exiting.")

    # 4. Context-Managed Execution
    # Remote uses Fabric's cd(); Local uses standard contextlib.chdir()
    with ctx.cd(str(work_path)) if is_remote else chdir(work_path):
        if (is_remote and exists(ctx, args.log_file)) or (not is_remote and Path(args.log_file).exists()):
            print(f"[*] Found cache in {work_path}/{args.log_file}. Done.")
            return 0

        print(f"[!] Running command in {work_path}...")
        result = ctx.run(f"{args.cmd} > {args.log_file}", warn_only=True)

        return 0 if result.ok else 1


if __name__ == "__main__":
    ret = run_cached_fab(sys.argv)
    sys.exit(ret)
