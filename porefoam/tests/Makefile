testDir ?= $(abspath ../../../runs/tests)
refDir ?= $(abspath .)

all: test

testDirs:
	@mkdir -p $(testDir)/pytest2f $(testDir)/pytest1f

# Run the 2f regression tests via pytest (equivalent to src/porefoam2f/test2f)
test: testDirs
	MS_TEST_DIR=$(testDir) pytest -v -m regression

# Run all tests via pytest (fast + regression)
test-all: testDirs
	MS_TEST_DIR=$(testDir) pytest -v -m ""

# Run fast unit tests only via pytest (skip regression)
test-fast: testDirs
	MS_TEST_DIR=$(testDir) pytest -v

# Individual pytest targets
voxcylinder: testDirs
	MS_TEST_DIR=$(testDir) pytest -v test_pf2f_voxcylinder.py -m regression

voxcylinderFSF: testDirs
	MS_TEST_DIR=$(testDir) pytest -v test_pf2f_voxcylinderFSF.py -m regression

voxcylCFMesh: testDirs
	MS_TEST_DIR=$(testDir) pytest -v test_pf2f_voxcylCFMesh.py -m regression

voxcylCFMeshFSF: testDirs
	MS_TEST_DIR=$(testDir) pytest -v test_pf2f_voxcylCFMeshFSF.py -m regression

porefoam1f: testDirs
	MS_TEST_DIR=$(testDir) pytest -v test_porefoam1f.py

dict: testDirs
	MS_TEST_DIR=$(testDir) pytest -v test_foam_dict.py

# Compare generated test results between test2f and pytest2f
compare:
	@echo "Comparing summary stats between $(testDir)/test2f and $(testDir)/pytest2f:"
	@for f in $(testDir)/pytest2f/*_summary.txt; do \
		base=$$(basename $$f); \
		if [ -f "$(testDir)/test2f/$$base" ]; then \
			echo "=== Comparing $$base ==="; \
			python3 post_process.py $$f > /tmp/py_stats.txt; \
			python3 post_process.py $(testDir)/test2f/$$base > /tmp/mk_stats.txt; \
			diff -u /tmp/mk_stats.txt /tmp/py_stats.txt || true; \
		else \
			echo "Note: $(testDir)/test2f/$$base not present"; \
		fi; \
	done

clean:
	rm -rf $(testDir)/pytest2f $(testDir)/pytest1f

.PHONY: all testDirs test test-all test-fast voxcylinder voxcylinderFSF voxcylCFMesh voxcylCFMeshFSF porefoam1f dict compare clean
