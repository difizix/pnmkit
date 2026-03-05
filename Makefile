
help:
	@echo "Available target commands:"
	@echo "  make all          # Re-install package and update stubs, slow"
	@echo "  make install      # Install the package into venv"
	@echo "  make test         # Run tests"
	@echo "  make test_integrations         # Run integration tests, slow"
	@echo "  make dev          # Fast incremental build for development"
	@echo "  make dev_test     # Run tests"
	@echo "  make dev_test_integrations     # Run integration tests"
	@echo "  make format file=path/to/file  # Format a specific python file or all files"
	@echo "For running indivudial tests use, e.g.:"
	@echo "  PYTHONPATH=build/install:.:src:image3kit/src .venv/bin/python tests/pnmkit/test_xpm_tutorials.py"
	@echo "  PYTHONPATH=build/install:.:src:image3kit/src .venv/bin/python tests/pnmkit/test_runPlotPNMs.py"

file ?= ""
format_strings:
	@[ -f .venv/bin/ruff ] || (set -x && .venv/bin/python -m pip install ruff flynt)
	@echo "Formatting $(file)..."
	test -n "$(file)" || ! printf "\nMissing arg, usage:\n""make format_strings file=\n\n"
	.venv/bin/python -m ruff check --select Q --fix $(file)
	.venv/bin/python -m flynt -tc $(file)


pyPip=.venv/bin/python -m pip
all: setup_venv
	${pyPip} uninstall -y pnmkit || true
	rm -f src/pnmkit/_pnmkit.so
	${pyPip} install .
	@$(MAKE) stubgen
	@$(MAKE) pre-commit
	@$(MAKE) test

VERSION := $(shell grep "^version =" pyproject.toml | cut -d '"' -f 2)

dev: setup_venv
	.venv/bin/cmake -S . -B build -DCMAKE_INSTALL_PREFIX=inst -DSKBUILD_PROJECT_VERSION=$(VERSION)
	.venv/bin/cmake --build build --verbose -j
	CMAKE_INSTALL_MODE=SYMLINK_OR_COPY .venv/bin/cmake --install build
	$(MAKE) dev_test

dev_test:
	PYTHONPATH=inst:image3kit/src .venv/bin/python -m pytest -m "not integration"

dev_test_integrations:
	PYTHONPATH=inst:image3kit/src .venv/bin/python -m pytest -m integration tests/pnmkit -v -s

stubgen:
	@[ -f .venv/bin/pybind11-stubgen ] || (set -x && ${pyPip} install pybind11-stubgen)
	.venv/bin/pybind11-stubgen pnmkit --output-dir src

install: setup_venv
	${pyPip} install --no-build-isolation -e .

uninstall:
	${pyPip} uninstall -y pnmkit || true

test:
	@[ -f .venv/bin/pytest ] || (set -x && ${pyPip} install pytest)
	.venv/bin/python -m pytest -m "not integration"

test_integrations:
	@[ -f .venv/bin/pytest ] || (set -x && ${pyPip} install pytest)
	.venv/bin/python -m pytest -m integration

.PHONY: setup_venv clean build test all stubgen pre-commit install help dev dev_test dev_test_integrations

setup_venv:
	@[ -d .venv ] || python3 -m venv .venv
	${pyPip} install cmake pre-commit scikit-build-core pybind11 pytest
	@if [ ! -f build/Makefile ]; then \
		.venv/bin/cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DSKBUILD_PROJECT_VERSION=$(VERSION); \
	fi
	ln -sf build/compile_commands.json ./
	@echo ========= env setup done =========

clean:
	rm -rf build compile_commands.json src/pnmkit/*.so

pre-commit:
	.venv/bin/pre-commit run -a || .venv/bin/pre-commit run -a \
	|| ! printf "\nThe following might help: \n%s\n\n" ".venv/bin/ruff check --unsafe-fixes --fix"
