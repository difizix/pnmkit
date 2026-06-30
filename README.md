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
* **Network Visualization:** Convert pore network simulation results into high-resolution screenshots and animations:
  * [`xdmf_3dl_screenshot.py`](./xdmf_3dl_screenshot.py): Captures 3D screenshots from `skelor` and `snflow` XDMF outputs.
  * [`xdmf_4dl_animate.py`](./xdmf_4dl_animate.py): Generates spatiotemporal 4D animations of two-phase flow simulation results.
* **Core Processing & Plotting:** Modules for pore-network data manipulation ([`process.py`](./process.py)), model abstraction ([`models.py`](./models.py)), and visualization ([`plots.py`](./plots.py)).
* **Ecosystem Integration:** Designed to integrate as a submodule with [porgui](https://github.com/difizix/porgui).

---

## Installation

```bash
git clone https://github.com/difizix/pnmkit.git
cd pnmkit
pip install -e .
