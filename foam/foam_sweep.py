"""Parameter grid expansion (Phase 1 — Generic core).

Generic itertools.product driver for multi-parameter sweeps. Preserves the
nesting order the caller passes — solver-specific naming/directory formatting
lives in foam_variants/.
"""

from collections.abc import Iterator
from itertools import product
from typing import Any


def expand_param_grid(**param_lists) -> Iterator[dict[str, Any]]:
    """Expand parameter lists into a full Cartesian product grid.

    The caller provides parameter names as keyword arguments, each mapping to
    an iterable of values. The generator yields one dict per combination, in
    the order of itertools.product(param_lists.values()), i.e. the rightmost
    parameter varies fastest.

    Example:
        >>> list(expand_param_grid(a=[1, 2], b=["x", "y"]))
        [{'a': 1, 'b': 'x'}, {'a': 1, 'b': 'y'}, {'a': 2, 'b': 'x'}, {'a': 2, 'b': 'y'}]

    This matches how bash scripts use nested for-loops: the first (outermost)
    parameter changes slowest, the last (innermost) changes fastest.

    Args:
        **param_lists: Parameter names → iterables of values.

    Yields:
        One dict per grid point, with keys matching the parameter names.
    """
    if not param_lists:
        yield {}
        return

    # Preserve insertion order (Python 3.7+ guarantees this).
    names = list(param_lists.keys())
    values = list(param_lists.values())

    for combo in product(*values):
        yield dict(zip(names, combo))


def parse_list(val: str) -> list:
    """Parse a space-separated string into a list, converting to int/float where possible.

    Each token is tried as int, then float, then kept as a string. Used to
    turn CLI sweep arguments (e.g. "--RSpheres '10 20 30'") into value lists
    for expand_param_grid().
    """
    items = val.split()
    result = []
    for item in items:
        try:
            result.append(int(item))
        except ValueError:
            try:
                result.append(float(item))
            except ValueError:
                result.append(item)
    return result

