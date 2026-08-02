# pnmkit.foam

Generic, solver-agnostic OpenFOAM utilities: case management, dictionary
editing, meshing, parameter sweeps, voxel-image handling, log post-processing,
and VTK-based visualization.

`foam/` knows nothing about any specific solver (`interFaceFoam`, `icoNSFoam`,
...) or any solver's dictionary keys.
Solver-specific policy lives in sibling packages such as `pnmkit.porefoam`,
which only ever imports *from* `foam/` — never the other way round. The
litmus test for whether something belongs here: if it only deals with
*mechanism* (how to run an OpenFOAM utility, how to parse/edit a dict, how to
mesh a surface, how to rewrite a voxel-image header) it's `foam/`; if it
encodes *policy* (which dict keys or solver a specific workflow cares about)
it belongs in the solver-specific package instead.

## Modules

### Case management — `foam_case.py`

- `FoamCase(case_dir)`: thin wrapper around running OpenFOAM utilities in a
  case directory — `run_app`, `run_mpi`, `run_distributed`, `run_mode` (pick
  serial/parallel/distributed from a string), `run_solver`, `decompose_par`,
  `renumber_mesh`, `check_mesh`, `smooth_f_mesh`, `transform_points`, `edit`
  (dict edits, see below). All `run_*` methods log to `log.<app>` and skip
  re-running if that log already exists (remove it to force a re-run).
- `read_points_bbox(mesh_dir)`: bounding box from `log.checkMesh` or
  `constant/polyMesh/points`, running `checkMesh` if neither is available yet.
- `darcy_flow_rate_from_bbox(bbox, darcy_velocity_um_s)`: inlet-face flow rate
  from a bounding box and a Darcy velocity.
- `CaseTemplateRunner`: base class for "copy a case template → mesh it via a
  `GeometryBuilder` → apply dict edits" workflows. Subclass this for a new
  solver-specific case runner; call `setup_mesh_case(...)` for the generic
  copy/build/edit sequence and add only what's actually solver-specific
  around it (see `pnmkit.porefoam.porefoam1f_case.SinglePhaseCaseRunner` for
  an example subclass).

```python
from pnmkit.foam import FoamCase

case = FoamCase("run/case1")
case.run_app("checkMesh")
case.run_mpi("interFoam", np=4)
```

### Dictionary editing — `foam_dict.py`

- `FileKV(file, entry, value, optional=False, insert_if_missing=False)`:
  one dict edit. `entry` is either `"keyword"` (whole-file match) or `"section.keyword"`
  (scoped to that brace-depth block). At most one dot is allowed.
- `apply_edits(case_dir, edits)`: applies a list of `FileKV` edits. Raises by
  default if a keyword/section isn't found; pass `optional=True` to skip
  instead, or `insert_if_missing=True` to insert `keyword value;` before the
  block's closing brace when the keyword isn't already present.

```python
from pnmkit.foam import FileKV, apply_edits

apply_edits(case_dir, [
    FileKV("system/controlDict", "endTime", "0.2"),
    FileKV("0/p", "Right.value", "uniform 500", insert_if_missing=True),
])
```

### Meshing — `foam_mesh.py` and `foam/geo/`

- `GeometryBuilder` protocol: anything with a
  `build(case, params) -> MeshBuildResult` method. Pass one to
  `CaseTemplateRunner`/a case runner to control how a case gets meshed.
- `VoxelImageGeometry`: voxel image → FOAM mesh directly (via `image3kit`'s
  `to_foam()`, or the external `voxelToFoam`/`voxelToFoamPar` executables) —
  no surface/STL step. Shared as-is by `porefoam1f` and `porefoam2f`.
- For mesh strategies that *do* go through an STL surface, mesh generation
  splits into two independent, composable pieces:
  - `SurfaceBuilder` protocol (`build_surface(case, params) -> Path`): how to
    get an STL. Implementations: `ScadSurfaceBuilder` (OpenSCAD →
    `surfacePointMerge` → `surfaceAutoPatch`), `VoxelSurfaceBuilder` (voxel
    image → STL via `image3kit.to_surf_mesh()` or `vxlToSurf`),
    `ExternalStlSurfaceBuilder` (stage an existing STL into the case dir).
  - `MeshBackend` protocol (`mesh_surface(case, stl_path, params) -> MeshBuildResult`):
    how a surface becomes a volume mesh. `CfMeshBackend` covers cfMesh's
    `cartesianMesh`/`cartesian2DMesh`, 2D/3D and one-pass/two-pass, with
    smoothing. A future `SnappyHexMeshBackend` would slot in here and work
    with every existing `SurfaceBuilder` for free.
- `foam/geo/` holds the concrete `GeometryBuilder` classes built by composing
  one `SurfaceBuilder` + one `MeshBackend` for a specific synthetic geometry —
  `foam/geo/spack.py` (`SpackGeometry`), `star.py` (`StarGeometry`), `tri.py`
  (`TriGeometry`), `stl.py` (`StlGeometry`), `cfmesh.py` (`CFMeshGeometry`).
  These only ever touch `system/meshingDict`/`system/meshDict` (mesh
  generation) — never `fvSolution`/`controlDict` (solver policy) — which is
  what keeps them here rather than in `pnmkit.porefoam`.
  Each module also exposes a matching CLI-argument/sweep triple —
  `add_geometry_args(parser)`, `build_geometry(args)`,
  `geometry_param_grid(args)` — so a driver script can compose geometry args
  with its own solver-policy args before parsing once (see
  `pnmkit.porefoam.spack` for how this is wired up with a `get_parser()`).

### Parameter sweeps — `foam_sweep.py`

- `expand_param_grid(**param_lists)`: Cartesian-product generator over named
  parameter lists, yielding one dict per grid point (rightmost parameter
  varies fastest, matching nested bash for-loops).
- `parse_list(val)`: parse a space-separated CLI string into a list of
  int/float/str values (`"10 20.5 foo"` → `[10, 20.5, "foo"]`).

```python
from pnmkit.foam import expand_param_grid
from pnmkit.foam.foam_sweep import parse_list

for params in expand_param_grid(RSphere=parse_list("15 20"), theta0=parse_list("140 150")):
    ...
```

### Voxel-image handling — `foam_image.py`

- `convert_voxel_image(src, dst, dtype=None, threshold=None, case=None)`:
  convert/threshold a voxel image (via `image3kit`, falling back to the
  `voxelImageProcPy` executable).
- `make_alpha_field(corners_mhd, alpha_mhd, threshold, unit, case=None)`:
  build an `alpha1` saturation field from a corners/skeleton image.
- `grow_alpha_field(alpha_mhd, n_grow, invert=False, case=None)`: grow/shrink
  an alpha field via `voxelAlphaFieldToFoam`.
- `find_image_file(stem, directory, extensions=(...))`: find an image file by
  stem, trying `.mhd`/`.nhdr`/`.tif`/`.am`/`.mhd.gz`/`.nhdr.gz` in order.
- `rewrite_mhd_header(path, unit=None, element_data_file=None, append_text=None)`:
  in-place `.mhd` header edits — substitute `Unit = ...`/`ElementDataFile = ...`
  and/or append text (e.g. a `threshold ...` line).

### Running a packaged case — `foam_run.py`

CLI/library for running a `.tar.gz`/`.zip`-packaged OpenFOAM case end to end:
`extract_of_case`, `edit_foam_case` (thin wrapper over `apply_edits`), and
`foam_sim(case_tgz, edits)` which extracts, applies edits, runs `Allrun` (or
the app named in `controlDict`), and repackages the result.

```bash
python -m pnmkit.foam.foam_run case.tar.gz
```

### Log post-processing — `foam_postprocess.py`

Pure-Python, column-name-agnostic parsing of `key = value` solver log lines
and tolerance comparisons against reference values — no OpenFOAM binaries
required: `parse_log_line`, `parse_log_file`, `compute_column_stats`,
`test_avg`, `print_stats`, `compare_logs`, `ToleranceResult`. See
`pnmkit/porefoam/tests/post_process.py` for a solver-specific wrapper built
on top of this.

### Visualization — `utils_foamvtk.py`, `foam_animate.py`, `foam_screenshot.py`

- `utils_foamvtk.py`: `FoamReader` and VTK pipeline helpers (`apply_filters`,
  `update_pipeline`, `adjust_camera`, `save_screenshot`, `set_colorbar_get_info`)
  shared by the two CLI scripts below.
- `foam_animate.py`: renders a field over every timestep in a case to a PNG
  sequence.
- `foam_screenshot.py`: renders one timestep's fields to `figs/` (`-i/--time-index`, default -1 = last).

```bash
python -m pnmkit.foam.foam_animate --case run/case1 --fields p U
python -m pnmkit.foam.foam_screenshot --case run/case1 --fields p U -i -1
```

### System utilities — `utils_sys.py`

Generic shell/process helpers with no OpenFOAM awareness: `run_shell`,
`run_shell_monitor` (streams output to a callback), `TaskMonitor` (background
`top`/`tail` logger for long-running jobs).

## Use case: the porefoam test suite

[`pnmkit/porefoam/tests/`](../porefoam/tests/README.md) is a concrete,
runnable example of most of the above working together: its standalone
runners and pytest suites build `FoamCase`/`CaseTemplateRunner`-based
single- and two-phase cases, mesh them with `VoxelImageGeometry`, apply
`FileKV`/`apply_edits` dict edits, sweep parameters with
`expand_param_grid`, and check results with `foam_postprocess`-style log
parsing. Start there — particularly `porefoam/tests/voxcylinder.py` — for a
worked example of wiring these `foam/` pieces into an actual simulation
before writing a new one.
