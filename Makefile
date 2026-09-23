.PHONY: all setup doctor test test-avtp run run-avtp gui patches
all:
	./scripts/build-libraries.sh
setup:
	./scripts/setup.sh
doctor:
	./scripts/doctor.sh
test:
	python3 tests/test_canfd.py
	python3 tests/test_mixed.py
	python3 tests/test_avtp.py
test-avtp:
	python3 tests/test_avtp.py
run:
	./scripts/run-mixed.sh Mixed
run-avtp:
	./scripts/run-mixed.sh AvtpTscf
gui:
	./scripts/run-gui.sh Mixed
patches:
	python3 scripts/export-patches.py
