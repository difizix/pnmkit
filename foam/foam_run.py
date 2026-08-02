import shutil
import sys
from os import PathLike
from pathlib import Path

from collections.abc import Sequence

from .foam_dict import FileKV, apply_edits
from .utils_sys import run_shell_monitor


def extract_of_case(case_tgz: PathLike) -> Path:
    "Extract a tar.gz / zip compressed OpenFOAM case, return case folder"
    extract_dir = Path(case_tgz).with_suffix("").with_suffix("").name
    print(f" Extracting to {extract_dir}:")
    shutil.unpack_archive(case_tgz, extract_dir=extract_dir)
    print("\n".join(str(p) for p in Path(extract_dir).glob("*")))
    cases = list(Path(extract_dir).rglob("system/controlDict"))
    assert len(cases) == 1, f"expected {case_tgz} with only one system/controlDict, got: {cases}"
    return cases[0].parents[1]


def edit_foam_case(case_dir: Path, edits: Sequence[FileKV]) -> None:
    """Modify the specified OpenFOAM parameters in the case.

    Delegates to foam_dict.apply_edits for brace-depth-aware editing.
    """
    apply_edits(case_dir, edits)


def foam_sim(case_tgz: PathLike, edits: Sequence[FileKV] | None):
    """Run an OpenFOAM case.tar.gz or .zip and wire out the results for post-processing"""

    case = extract_of_case(case_tgz)

    shout = lambda s: print(s.encode("utf-8"), "text/plain")

    shout("Files before run:\n" + "\n  ".join(sorted(str(p) for p in Path(case).glob("*"))) + "\n")

    if edits:
        edit_foam_case(case, edits)

    run_shell_monitor(
        f"""/bin/bash -c '
    [ -n "$WM_PROJECT_DIR" ] || source /home/$HOME/.bashrc
    set -e
    run_dir=$PWD/{case}
    echo "$0 '$run_dir'"
    set -ex
    if [ -f "$run_dir/Allrun" ]; then
        chmod +x "$run_dir/Allrun"
        (cd "$run_dir" && ./Allrun)
    else
        application=`grep application $run_dir/system/controlDict | sed 's/application\\s*\\(.*Foam\\)\\s*;/\1/g'`
        if ! which "$application"; then
            echo "Error, application ($application) in $run_dir/system/controlDict is missing"
            exit 1
        fi
        (cd "$run_dir" && "$application")
    fi
    '""",
        shout,
    )

    shout("Files after run:\n" + "\n  ".join(sorted(str(p) for p in case.glob("*"))) + "\n")

    return shutil.make_archive(case.name, "gztar", root_dir=case)


if __name__ == "__main__":  # local run for testing
    foam_sim(sys.argv[1:])
