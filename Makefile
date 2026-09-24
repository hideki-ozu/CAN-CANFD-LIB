.PHONY: all setup doctor test test-avtp test-someip test-protection test-av run run-avtp run-someip run-protection run-av gui patches
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
	python3 tests/test_someip.py
	python3 tests/test_protection.py
	python3 tests/test_av.py
test-avtp:
	python3 tests/test_avtp.py
test-someip:
	python3 tests/test_someip.py
test-protection:
	python3 tests/test_protection.py
test-av:
	python3 tests/test_av.py
run:
	./scripts/run-mixed.sh Mixed
run-avtp:
	./scripts/run-mixed.sh AvtpTscf
run-someip:
	./scripts/run-someip.sh SomeIpTcpUdp
run-protection:
	./scripts/run-mixed.sh E2eSecOcAvtp
run-av:
	./scripts/run-av.sh AvTsnGptp
gui:
	./scripts/run-gui.sh Mixed
patches:
	python3 scripts/export-patches.py
