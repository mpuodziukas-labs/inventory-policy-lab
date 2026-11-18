PY ?= python3

.PHONY: test selftest regen

test:
	$(PY) -m pytest -q -p no:cacheprovider

selftest:
	$(PY) lab/selftest.py

regen:
	$(PY) lab/regen.py
