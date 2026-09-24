# Third-party notices

This repository distributes patches and setup tooling. Upstream repositories
are fetched from their original public locations at the commits recorded in
`sources.lock.json`; their full source, notices, and licenses remain in the
resulting `upstream/` checkouts. No OMNeT++ binary or source distribution is
included in this Git repository.

| Patch / dependency | Upstream | License and attribution |
|---|---|---|
| `patches/FiCo4OMNeT.patch` | [CoRE-RG/FiCo4OMNeT](https://github.com/CoRE-RG/FiCo4OMNeT) | BSD 3-Clause; CoRE Research Group, Hamburg University of Applied Sciences. See `LICENSES/FiCo4OMNeT-BSD-3-Clause.txt`. Some existing individual files carry LGPL notices; preserve those file notices as well. |
| `patches/CoRE4INET.patch` | [CoRE-RG/CoRE4INET](https://github.com/CoRE-RG/CoRE4INET) | LGPL-3.0-or-later notices in modified source; original authors and notices retained. See `LICENSES/CoRE4INET-LGPL-3.0.txt`. |
| `patches/SignalsAndGateways.patch` | [CoRE-RG/SignalsAndGateways](https://github.com/CoRE-RG/SignalsAndGateways) | LGPL-3.0-or-later notices in modified source; original notices retained. See `LICENSES/SignalsAndGateways-LGPL-3.0.txt`. |
| `patches/SOA4CoRE.patch` | [CoRE-RG/SOA4CoRE](https://github.com/CoRE-RG/SOA4CoRE) | LGPL-3.0; CoRE Research Group, HAW Hamburg. The INET4 port lives in `src-inet4/` (copied and modified upstream files keep their notices; new files carry LGPL notices). See `LICENSES/SOA4CoRE-LGPL-3.0.txt`. |
| INET (fetched, unmodified) | [inet-framework/inet](https://github.com/inet-framework/inet) | LGPL; see `LICENSES/INET-LGPL-3.0.txt` and per-file notices in the fetched source. |
| Open1722 (fetched, unmodified, test-only) | [COVESA/Open1722](https://github.com/COVESA/Open1722) | BSD 3-Clause; Intel Corporation, COVESA and contributors (see `upstream/Open1722/LICENSE`). Compiled only into the local test helpers `.local/bin/open1722_decode` and `.local/bin/open1722_media_decode`; not linked into or distributed with the simulation libraries. |

| Wireshark IEEE 1722 dissector, OpenAvnu (consulted only) | [wireshark/wireshark](https://gitlab.com/wireshark/wireshark), [Avnu/OpenAvnu](https://github.com/Avnu/OpenAvnu) | Consulted for the IEC 61883-4 / CIP field layout of the AV stream model; no source code is copied or distributed. |
| OpenSSL 3 libcrypto (system library, not distributed) | [openssl/openssl](https://github.com/openssl/openssl) | Apache-2.0. `autosar/` links dynamically against the installed libcrypto for AES-128-CMAC (`EVP_MAC`). `scripts/fetch-openssl-dev.sh` may unpack the distribution's `libssl-dev` headers into `.local/openssl-dev`; they are not committed or redistributed. |
| autosar-e2e 1.0.0 (downloaded by the test, test-only) | [zariiii9003/autosar-e2e](https://github.com/zariiii9003/autosar-e2e) | MIT; Artur Drogunow. Installed from PyPI (hash-pinned in `tests/protectiontest/requirements.txt`) into `.local/venv-protection-test` as the independent E2E reference in `tests/test_protection.py`. The E2E known-answer values in `autosar/src/autosar/test/ProtectionSelfTest.cc` are the protocol examples also used by its test suite; no source code is copied. |
| pycryptodome 3.23.0 (downloaded by the test, test-only) | [Legrandin/pycryptodome](https://github.com/Legrandin/pycryptodome) | BSD-2-Clause / public domain (see its LICENSE). Same venv; independent AES-CMAC reference. Not linked into or distributed with the simulation libraries. |
| Scapy 2.6.1 (downloaded by the test, test-only) | [secdev/scapy](https://github.com/secdev/scapy) | GPL-2.0; installed from PyPI (hash-pinned in `tests/someiptest/requirements.txt`) into `.local/venv-someip-test` and run as a separate process to decode captured SOME/IP frames. Not linked into, copied into or distributed with this repository or the simulation libraries. |

A copy of GPLv3, referenced by LGPLv3, is provided in `LICENSES/GPL-3.0.txt`.
New source additions within the patches declare their license in their headers.
The top-level BSD license does not replace any upstream license.

Local modifications add CAN-FD metadata, validation and approximate timing to
FiCo4OMNeT; migrate the selected CoRE background application to INET4; and adapt
CAN gateway applications plus a new INET4 packet bridge and an IEEE 1722 (AVTP)
ACF CAN gateway in SignalsAndGateways; add E2E/SecOC-protected CAN applications to
SignalsAndGateways, a transmission hook to FiCo4OMNeT and E2E/SecOC for SOME/IP
events to the SOA4CoRE INET4 port. The AUTOSAR E2E/SecOC library in `autosar/` is
original code of this repository (BSD 3-Clause) written from the protocol
descriptions; it is not an AUTOSAR-licensed implementation. The IEEE 1722 field layout was implemented
from the standard's field definitions and cross-checked against Open1722; no
Open1722 source code is copied into the patches.
These are independent local changes, not upstream releases or endorsements.

OMNeT++ remains separately installed under its own license. The optional
runtime downloader obtains the official archive directly; refer to the
license distributed with that archive for its terms.
