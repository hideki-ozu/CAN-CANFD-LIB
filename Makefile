.PHONY: all setup doctor test run gui patches
all:
	./scripts/build-libraries.sh
setup:
	./scripts/setup.sh
doctor:
	./scripts/doctor.sh
test:
	python3 tests/test_canfd.py
	python3 tests/test_mixed.py
run:
	./scripts/run-mixed.sh Mixed
gui:
	./scripts/run-gui.sh Mixed
patches:
	python3 scripts/export-patches.py
