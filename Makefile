
help:
	@echo "Install prerequisite using commands:"
	@echo "  python -m venv .venv"
	@echo "  source .venv/bin/activate"
	@echo "  pip install pybind11-stubgen numpy pytest"
	@echo
	@echo "Available target commands:"
	@echo "  make all          # Re-install package and update stubs"
	@echo "  make install      # Install the package into venv"
	@echo "  make test         # Run tests"
	@echo "  make dev          # Fast incremental build for development"

all: setup_venv
	.venv/bin/pip uninstall -y pnmkit || true
	rm -f src/pnmkit/_pnmkit.so
	.venv/bin/pip install --no-build-isolation -e .
	@$(MAKE) stubgen
	@$(MAKE) pre-commit
	@$(MAKE) test

dev: setup_venv
	.venv/bin/pip uninstall -y pnmkit || true
	.venv/bin/cmake --build build -j
	cp build/_pnmkit*.so src/pnmkit/_pnmkit.so
	@$(MAKE) test

stubgen:
	@[ -f .venv/bin/pybind11-stubgen ] || (set -x && .venv/bin/pip install pybind11-stubgen)
	.venv/bin/pybind11-stubgen pnmkit --output-dir src

install: setup_venv
	.venv/bin/pip install --no-build-isolation -e .

test:
	@[ -f .venv/bin/pytest ] || (set -x && .venv/bin/pip install pytest)
	.venv/bin/pytest

.PHONY: setup_venv clean build test all stubgen pre-commit install help dev

setup_venv:
	@[ -d .venv ] || python3 -m venv .venv
	.venv/bin/pip install cmake pre-commit scikit-build-core pybind11
	.venv/bin/cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
	ln -sf build/compile_commands.json ./

clean:
	rm -rf build compile_commands.json

pre-commit:
	.venv/bin/pre-commit run -a || .venv/bin/pre-commit run -a
