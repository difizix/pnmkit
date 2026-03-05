# pnmkit

> [!WARNING]
> * This is a temporary repository for developing and benchmarking its submodules.
> * Access to private `snm` submodule is required to clone the full repo, contact *Ali Q Raeini* for more info.

To clone the full repo:
```
git clone --recursive git@github.com:ai4netzero/pnmkit.git
```

Only tested in Linux atm:
run `make` to see available make targets.


# License

The source code is licensed under the [GNU AGPLv3](https://www.gnu.org/licenses/agpl-3.0.txt), see [LICENSE](LICENSE).

It contains submodules that have different licenses:

- [xpm](https://github.com/image3kit/xpm): [GNU GPLv3](https://www.gnu.org/licenses/gpl-3.0.txt)
- [snm](https://github.com/image3kit/snm): [GNU AGPLv3](https://www.gnu.org/licenses/agpl-3.0.txt), [NOTICE](./snm/NOTICE)
- [image3kit](https://github.com/image3kit/image3kit): [BSD 3-Clause](https://opensource.org/licenses/BSD-3-Clause)

- The snm submodule includes a modified version of [pnflow](https://github.com/aliraeini/pnm) code, for reference/cbenchmarking.
- The xpm submodule includes a copy of the [pnextract](https://github.com/ImperialCollegeLondon/pnextract) code.

- Other packages: see the Cmakelists.txt and the pyproject.toml files.
