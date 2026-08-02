"""Log parsing and tolerance comparison (Phase 1 — Generic core).

Ported from src/porefoam2f/test2f/post_process.py, kept independent of
which columns/solver produced the log.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from . import runtime as rt

# Default number of initial lines to skip when computing mean/min/max stats
# (matches test2f/post_process.py:7).
NSKIP_DEFAULT = 20


@dataclass
class ToleranceResult:
    """Result of a tolerance comparison."""

    variable: str
    computed: float
    reference: float
    relative_diff: float
    tolerance: float
    passed: bool

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.variable}: {self.computed:.6g} ?= {self.reference:.6g}, dif={self.relative_diff:.4g} ?< tol={self.tolerance:.4g}"


def parse_log_line(line: str) -> dict[str, float]:
    """Parse a single line of OpenFOAM-style `Key = Value` log output.

    Regex matches: key (word chars) = numeric value (float/sci notation).
    Ignores trailing units or extra text.

    Example:
        >>> parse_log_line("Time = 0.001 Pc = 7000.5 Unit = Pa Uavg = 1.2e-4")
        {'Time': 0.001, 'Pc': 7000.5, 'Uavg': 1.2e-04}
    """
    matches = re.findall(r"(\w+)\s*=\s*([0-9eE.+-]+)\s+", line)
    data: dict[str, float] = {}
    for key, val_str in matches:
        key = key.strip()
        try:
            data[key] = float(val_str.strip())
        except ValueError:
            pass  # skip non-numeric values
    return data


def parse_log_file(log_file: Path | str, columns: list[str] | None = None) -> list[dict[str, float]]:
    """Parse an entire log file into a list of row dicts.

    Each row contains the key/value pairs extracted from that line.
    Lines with no matching keys become empty dicts (preserves row count).

    Args:
        log_file: Path to the log file (e.g. summary.txt, log.interFaceFoam).
        columns: Optional list of expected column names for type hints.

    Returns:
        List of dicts, one per line.
    """
    log_file = Path(log_file)
    if not log_file.exists():
        msg = f"Log file not found: {log_file}"
        raise FileNotFoundError(msg)

    rows: list[dict[str, float]] = []
    with open(log_file) as f:
        for line in f:
            rows.append(parse_log_line(line))
    return rows


def compute_column_stats(
    rows: list[dict[str, float]],
    column: str,
    nskip: int = NSKIP_DEFAULT,
) -> dict[str, float]:
    """Compute mean/min/max statistics for a column, skipping initial transient rows.

    Args:
        rows: Parsed log rows.
        column: Column name.
        nskip: Number of initial rows to skip.

    Returns:
        Dict with keys: avg, min, max, count.

    Raises:
        ValueError: If the column is missing from all rows after nskip.
    """
    import statistics

    values = []
    for row in rows[nskip:]:
        if column in row:
            values.append(row[column])

    if not values:
        msg = f"Column '{column}' not found in rows after skipping {nskip} lines"
        raise ValueError(msg)

    return {
        "avg": statistics.mean(values),
        "min": min(values),
        "max": max(values),
        "count": len(values),
    }


def test_avg(
    log_file: Path | str,
    variable: str,
    reference: float,
    tolerance: float,
    nskip: int = NSKIP_DEFAULT,
) -> ToleranceResult:
    """Compare the mean of a log column against a reference value with tolerance.

    Reproduces test2f/post_process.py's `test_avg` command-line mode.

    Args:
        log_file: Path to the log file.
        variable: Column name to test.
        reference: Reference value to compare against.
        tolerance: Relative tolerance (e.g. 0.05 = 5%).
        nskip: Number of initial rows to skip.

    Returns:
        ToleranceResult describing the comparison.

    Raises:
        AssertionError: If the tolerance check fails.
    """
    rows = parse_log_file(log_file)
    stats = compute_column_stats(rows, variable, nskip=nskip)
    computed = stats["avg"]

    # Relative difference (handle zero reference).
    rel_diff = abs(reference - computed) / abs(reference) if reference != 0.0 else abs(reference - computed)

    passed = rel_diff <= tolerance
    result = ToleranceResult(
        variable=variable,
        computed=computed,
        reference=reference,
        relative_diff=rel_diff,
        tolerance=tolerance,
        passed=passed,
    )

    rt.disp(str(result))
    if not passed:
        msg = f"Tolerance check failed: {result}"
        raise AssertionError(msg)
    return result


def print_stats(rows: list[dict[str, float]], columns: list[str] | None = None, nskip: int = NSKIP_DEFAULT):
    """Print avg/min/max for each column (reproduces test2f/post_process.py print_stats).

    Args:
        rows: Parsed log rows.
        columns: Columns to print; if None, uses the union of all keys present.
        nskip: Rows to skip.
    """
    if not rows:
        return

    # Determine columns.
    if columns is None:
        columns_set: set[str] = set()
        for row in rows[nskip:]:
            columns_set.update(row.keys())
        columns = sorted(columns_set)

    for col in columns:
        try:
            stats = compute_column_stats(rows, col, nskip=nskip)
        except ValueError:
            rt.disp(f"{col}: <missing>")
            continue
        rt.disp(f"{col}_avg {stats['avg']:.6g}")
        rt.disp(f"{col}_min {stats['min']:.6g}")
        rt.disp(f"{col}_max {stats['max']:.6g}")


def compare_logs(
    log_a: Path | str,
    log_b: Path | str,
    variables: list[str] | None = None,
    tolerance: float = 0.05,
    nskip: int = NSKIP_DEFAULT,
) -> list[ToleranceResult]:
    """Compare average statistics of two log files column-by-column.

    Args:
        log_a: First log file.
        log_b: Second log file.
        variables: Columns to compare; if None, uses common columns.
        tolerance: Relative tolerance.
        nskip: Rows to skip.

    Returns:
        List of ToleranceResult for each variable.
    """
    rows_a = parse_log_file(log_a)
    rows_b = parse_log_file(log_b)

    if variables is None:
        cols_a = {k for row in rows_a for k in row}
        cols_b = {k for row in rows_b for k in row}
        variables = sorted(cols_a & cols_b)

    results: list[ToleranceResult] = []
    for var in variables:
        try:
            stats_a = compute_column_stats(rows_a, var, nskip=nskip)
            stats_b = compute_column_stats(rows_b, var, nskip=nskip)
        except ValueError:
            results.append(
                ToleranceResult(
                    variable=var,
                    computed=float("nan"),
                    reference=float("nan"),
                    relative_diff=float("inf"),
                    tolerance=tolerance,
                    passed=False,
                )
            )
            continue

        rel_diff = abs(stats_a["avg"] - stats_b["avg"]) / max(abs(stats_a["avg"]), 1e-30)
        passed = rel_diff <= tolerance
        results.append(
            ToleranceResult(
                variable=var,
                computed=stats_a["avg"],
                reference=stats_b["avg"],
                relative_diff=rel_diff,
                tolerance=tolerance,
                passed=passed,
            )
        )

    for r in results:
        rt.disp(str(r))
    return results
