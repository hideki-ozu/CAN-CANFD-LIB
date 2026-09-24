# AUTOSAR E2E/SecOC protection library (this repository, BSD-3-Clause).
.PHONY: all makefiles clean
all: makefiles
	$(MAKE) -C src MODE=release
makefiles:
	cd src && opp_makemake -f --deep --make-so -o AutosarProtection -O out -I.
clean:
	-$(MAKE) -C src MODE=release clean
