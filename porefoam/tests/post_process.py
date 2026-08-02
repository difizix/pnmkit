#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

NSkip = 20


# A function to parse a single line of the log file
def parse_log_line(line):
    # Regex to find all key-value pairs (e.g., 'Key = Value Unit')
    matches = re.findall(r'(\w+)\s*=\s*([0-9eE.+-]+)\s+', line)
    data = {}
    for match in matches:
        key = match[0].strip()
        value = float(match[1].strip())
        data[key] = value
    return data


def parse_data(log_file = 'log_data.txt'):
    parsed_data = []

    with Path(log_file).open() as f:
        for line in f:
            parsed_data.append(parse_log_line(line))
    df = pd.DataFrame(parsed_data)
    df['Time']    = df['Time'].astype(float)
    df['Pc']      = df['Pc'].astype(float)
    df['Uavg']    = df['Uavg'].astype(float)
    df['Umax']    = df['Umax'].astype(float)
    df['D_alpha'] = df['D_alpha'].astype(float)
    df['D_p']     = df['D_p'].astype(float)
    return df

def print_stats(df: pd.DataFrame):
    for column in df:
        print(column+'_avg', df.loc[NSkip:, column].mean())
        print(column+'_min', df.loc[NSkip:, column].min())
        print(column+'_max', df.loc[NSkip:, column].max())


def plot_df(df: pd.DataFrame, axs, labl, markr, colr):

    ax=axs[0,0]
    ax.plot(df['Time'], df['Pc'], label=labl, marker=markr, color=colr)
    ax.set_title('Capillary Pressure (Pc) vs. Time')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Pc (Pa)')
    ax.legend()
    ax.grid(True)

    ax=axs[1,0]
    ax.semilogy(df['Time'], df['Uavg'], marker=markr, color=colr)
    ax.set_title('Average Velocity (Uavg) vs. Time')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Uavg (m/s)')
    ax.grid(True)

    ax=axs[1,1]
    ax.semilogy(df['Time'], df['Umax'], marker=markr, color=colr)
    ax.set_title('Maximum of Velocity Field magnitude (Umax) vs. Time')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Umax (m/s)')
    ax.grid(True)

    ax=axs[0,1]
    ax.plot(df['Time'], df['D_p'], marker=markr, color=colr)
    ax.set_title('Dynamic Pressure Drop (D_p) vs. Time')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('D_p (m/s)')
    ax.grid(True)


def extract_summary(log_file: str | Path, summary_file: str | Path) -> Path:
    """Extract Umax lines from interFaceFoam log file to summary file."""
    log_path = Path(log_file)
    summary_path = Path(summary_file)
    lines = [line for line in log_path.read_text(errors="ignore").splitlines() if "Umax" in line]
    summary_path.write_text("\n".join(lines) + ("\n" if lines else ""))
    return summary_path


def check_avg(summary_file: str | Path, var: str, ref: float, tol: float, n_skip: int = NSkip) -> float:
    """Assert that the mean of var (skipping n_skip steps) matches ref within tol."""
    df = parse_data(str(summary_file))
    val = float(df.loc[n_skip:, var].mean())
    ref = float(ref)
    tol = float(tol)
    dif = abs(ref - val) / abs(ref) if ref != 0.0 else abs(ref - val)
    msg = f"In file {summary_file}, {var}:{val} ?= ref:{ref}, dif:{dif} ?<= tol:{tol}"
    print(msg)
    assert dif <= tol, f"Error: {msg}"
    return val


if __name__ == "__main__":
    # TODO: this shall by default look for all log.iInter... and if stats do not exist creates them, so that it can be used from Makefile rather that the test script. see the accompinying .sh files for its current usage, all calls shall be done after all simulations, allowing for all simulations to be run before test checks
    # use argparse instead?
    import sys
    if len(sys.argv) <= 1:
        print("Usage:")
        print(f"{sys.argv} voxylSnpCCF_Uo0w10CAw140_summary.txt")
        print("or ")
        print(f"{sys.argv} plot  A_summary.txt B_summary.txt")
        print("or ")
        print(f"{sys.argv} testeq  A_summary.txt  Variable  Value  Tolerance")
        print(f"{sys.argv} testeq  A_summary.txt    Pc_max  7000   0.05")
        sys.exit(0)
    arg2n = sys.argv[2:]
    arg1 = sys.argv[1]

    if arg1 == "plot":
        # Create the plots
        fig, axs = plt.subplots(2, 2, figsize=(10, 8))
        fig.suptitle('Simulation Data over Time', fontsize=16)
        markr=["x", "o", "<", ">"]
        colrs=["r", "g", "b", "c"]
        for ii,logf in enumerate(arg2n):
            df = parse_data(logf)
            nam = logf.replace('_summary','').replace('.txt','')
            plot_df(df, axs, nam, markr[ii], colrs[ii])

        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        print('Writing simulation_data_plot.svg')
        plt.savefig('simulation_data_plot.svg')

    elif arg1 == "test_avg":
        df = parse_data(arg2n[0])
        val = df.loc[NSkip: , arg2n[1]].mean()
        ref = float(arg2n[2])
        tol = float(arg2n[3])
        dif = abs(ref-val)/(abs(ref)) if ref != float('0') else abs(ref-val)
        msg = f"In file {arg2n[0]}, {arg2n[1]}:{val} ?= ref:{ref}, dif:{dif} ?< tol:{tol}"
        print(msg)
        msg = f"Error: {msg}"
        assert dif<=tol, msg
    else:
        df = parse_data(arg1)
        print_stats(df)
