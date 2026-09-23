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
| INET (fetched, unmodified) | [inet-framework/inet](https://github.com/inet-framework/inet) | LGPL; see `LICENSES/INET-LGPL-3.0.txt` and per-file notices in the fetched source. |

A copy of GPLv3, referenced by LGPLv3, is provided in `LICENSES/GPL-3.0.txt`.
New source additions within the patches declare their license in their headers.
The top-level BSD license does not replace any upstream license.

Local modifications add CAN-FD metadata, validation and approximate timing to
FiCo4OMNeT; migrate the selected CoRE background application to INET4; and adapt
CAN gateway applications plus a new INET4 packet bridge in SignalsAndGateways.
These are independent local changes, not upstream releases or endorsements.

OMNeT++ remains separately installed under its own license. The optional
runtime downloader obtains the official archive directly; refer to the
license distributed with that archive for its terms.
