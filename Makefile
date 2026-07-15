MkDIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ifneq (,$(wildcard ${MkDIR}.env))
    include ${MkDIR}.env
    export
endif
ifneq (,$(wildcard ${MkDIR}../.env))
    include ${MkDIR}../.env
    export
endif
# Alow global (out of source) build directory,
# if set via msBilDir, msDepDir and msPyDir:
msBilDir ?= ${MkDIR}/build
msDepDir ?= ${MkDIR}.deps
msPyDir ?= ${MkDIR}.venv

BinDir := ${msPyDir}/bin
PyExe := ${BinDir}/python
PyPip := ${PyExe} -m pip

help:
	@echo "Available target commands:"
	@echo "  make all          # Re-install package and update stubs, slow"
	@echo "  make install      # Install the package into venv"
	@echo "  make test         # Run tests"
	@echo "  make test_integrations         # Run integration tests, slow"
	@echo "  make dev          # Fast incremental build for development"
	@echo "  make dev_test     # Run tests"
	@echo "  make dev_test  test_dir=run1   # Run tests, keep results"
	@echo "  make dev_test_integrations     # Run integration tests"
	@echo "  make format file=path/to/file  # Format a specific python file or all files"
	@echo "For running indivudial tests use, e.g.:"
	@echo "  PYTHONPATH=build/install:.:src:image3kit/src ${PyExe} tests/pnmkit/test_xpm_tutorials.py"
	@echo "  PYTHONPATH=build/install:.:src:image3kit/src ${PyExe} tests/pnmkit/test_runPlotPNMs.py"

file ?= ""
format_strings:
	@[ -f ${BinDir}/ruff ] || (set -x && ${PyPip} install ruff flynt)
	@echo "Formatting $(file)..."
	test -n "$(file)" || ! printf "\nMissing arg, usage:\n""make format_strings file=\n\n"
	${PyExe} -m ruff check --select Q --fix $(file)
	${PyExe} -m flynt -tc $(file)


all: setup_venv
	${PyPip} uninstall -y pnmkit || true
	rm -f src/pnmkit/_pnmkit.so
	${PyPip} install -e .[test] \
		--config-settings=build-dir=$(msBilDir)/pnmkit \
		--config-settings=cmake.define.FETCHCONTENT_BASE_DIR=$(msDepDir)
	@$(MAKE) stubgen
	@$(MAKE) pre-commit
	@$(MAKE) test

VERSION := $(shell grep "^version =" pyproject.toml | cut -d '"' -f 2)

dev: setup_venv
	${BinDir}/cmake -G Ninja -S . -B $(msBilDir)/pnmkit -DCMAKE_INSTALL_PREFIX=.venv -DSKBUILD_PROJECT_VERSION=$(VERSION) -DFETCHCONTENT_BASE_DIR=$(msDepDir)
	${BinDir}/cmake --build $(msBilDir)/pnmkit --verbose -j
	CMAKE_INSTALL_MODE=SYMLINK_OR_COPY ${BinDir}/cmake --install $(msBilDir)/pnmkit
	$(MAKE) dev_test

test_dir ?=
pytest_args ?=
ifneq ($(test_dir),)
  pytest_args += --basetemp=$(test_dir)
endif

dev_test:
	PYTHONPATH=.venv:image3kit/src ${PyExe} -m pytest -m "not integration" $(pytest_args)

dev_test_integrations:
	PYTHONPATH=.venv:image3kit/src ${PyExe} -m pytest -m integration tests/pnmkit -v -s $(pytest_args)

stubgen:
	@[ -f ${BinDir}/pybind11-stubgen ] || (set -x && ${PyPip} install pybind11-stubgen)
	${BinDir}/pybind11-stubgen pnmkit --output-dir src

install: setup_venv
	${PyPip} install --no-build-isolation -e . \
		--config-settings=build-dir=$(msBilDir)/pnmkit \
		--config-settings=cmake.define.FETCHCONTENT_BASE_DIR=$(msDepDir)

uninstall:
	${PyPip} uninstall -y pnmkit || true

test:
	@[ -f ${BinDir}/pytest ] || (set -x && ${PyPip} install pytest)
	${PyExe} -m pytest -m "not integration"

test_integrations:
	@[ -f ${BinDir}/pytest ] || (set -x && ${PyPip} install pytest)
	${PyExe} -m pytest -m integration

.PHONY: setup_venv clean build test all stubgen pre-commit install help dev dev_test dev_test_integrations

setup_venv:
	@[ -d ${msPyDir} ] || python3 -m venv ${msPyDir}
	${PyPip} install cmake ninja pre-commit scikit-build-core pybind11 pytest
	@if [ ! -f $(msBilDir)/pnmkit/build.ninja ]; then \
		${BinDir}/cmake -G Ninja -S . -B $(msBilDir)/pnmkit -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DSKBUILD_PROJECT_VERSION=$(VERSION) -DFETCHCONTENT_BASE_DIR=$(msDepDir); \
	fi
	ln -sf $(msBilDir)/pnmkit/compile_commands.json ./
	@echo ========= env setup done =========

clean:
	rm -rf $(msBilDir)/pnmkit compile_commands.json src/pnmkit/*.so

pre-commit:
	${BinDir}/pre-commit run -a || ${BinDir}/pre-commit run -a \
	|| ! printf "\nThe following might help: \n%s\n\n" "${BinDir}/ruff check --unsafe-fixes --fix"

format-uncrustify:
	export PATH=${MkDIR}../uncrustify/build:$(PATH) && cd snm &&\
	find . -name "*.cpp" -o -name "*.h" -o -name "*.hpp" \
	  | xargs uncrustify -c uncrustify.cfg --no-backup --replace
