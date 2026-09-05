# PNMKit: Python Utilities for Pore-Scale Modeling

A set of Python utility scripts and modules for managing, processing, and visualizing pore-scale modeling workflows.

> [!WARNING]
> * **Experimental:** Unstable API subject to breaking changes.
> * **Experimental:** Unpublished external dependencies.

---

## Features

* **Simulation Orchestration:** Run network extraction and network flow simulations using:
  * [XPM](https://github.com/difizix/xpm) *(deprecated; contact H. Menke for details on newer alternatives)*
  * [snm (cnflow/snflow)](https://github.com/difizix/snm) *(WIP)*
* **Network Operations (`pnmkit.network_ops`):** Manipulate pore network geometry, seed extracted networks into XPM cache, parse invasion entry pressures, and adjust network shapes (e.g., equilateral conversions).
* **Network Visualization:** Convert pore network simulation results into high-resolution screenshots and animations:
  * [`xdmf_3dl_screenshot.py`](./xdmf_3dl_screenshot.py): Captures 3D screenshots from `skelor` and `snflow` XDMF outputs.
  * [`xdmf_4dl_animate.py`](./xdmf_4dl_animate.py): Generates spatiotemporal 4D animations of two-phase flow simulation results.
* **Core Processing & Plotting:** Modules for pore-network data manipulation ([`process.py`](./process.py)), model abstraction ([`models.py`](./models.py)), and visualization ([`plots.py`](./plots.py)).
* **Ecosystem Integration:** Designed to integrate as a submodule with [porgui](https://github.com/difizix/porgui).

---

## Architecture & Design Conventions

### 1. Minimal Public Top-Level API
`pnmkit/__init__.py` exposes strictly the top-level runner wrappers:
* `skelor` (and alias `mextract` / `snextract`)
* `pnextract`
* `scalor` (and alias `snflow`)
* `cnflow`
* `pnflow`
* `xpm`

All domain operations (network seeding, conversions, file parsing) are kept inside [`pnmkit.network_ops`](./network_ops.py).

### 2. Environment Variables via `extra_env`
Transient environment variables needed by backend processes should be passed directly inside the solver configuration dictionary (`kwrds`/`config`):
```python
config = {
    "Overwrite": "true",
    "NETWORK": "F tringu",
    "extra_env": {"CNM_DEBUG_PC": "1", "XPM_WRITE_NET_STATS": "1"}
}
cnflow(config)
```
The backend execution runners pop `"extra_env"` prior to writing config files (`.mhd`, `.json`) and apply them strictly to the subprocess environment.

### 3. Test Isolation & Cleanliness
All tests in `tests/` must isolate file creation:
* Always use pytest `tmp_path` fixture.
* Change directory using `monkeypatch.chdir(tmp_path)` to ensure generated simulation files never leak into repository root or package folders.

---

## Installation

```bash
git clone https://github.com/difizix/pnmkit.git
cd pnmkit
pip install -e .
```
