
To test compilation, build with a presistent cache:
```bash
pip install -e . --config-settings=build-dir=build
# (cd build && ninja > build_log.txt 2>&1 ) # in case build fails
```