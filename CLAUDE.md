# Setup instructions for Claude Code

Read README.md before executing setup. It is the complete user-facing installation guide.

- Assume the user already installed and tested OMNeT++; preserve that installation.
- Resolve OMNETPP_ROOT from the user's supplied path or active OMNeT++ environment.
- Run scripts/doctor.sh, then BUILD_JOBS=4 scripts/setup.sh (reduce jobs for low memory).
- Normal setup must not call build-runtime.sh or setup-runtime-deps.sh. Do not change OMNeT++ configure.user, system packages, shell startup files, or authentication settings.
- Sources are pinned by sources.lock.json. Preserve local edits: no reset/clean to bypass commit or patch mismatches.
- Success requires native CAN/CAN-FD tests, all four mixed network configurations the IEEE 1722 AVTP tests (tests/test_avtp.py), the SOME/IP tests (tests/test_someip.py), the E2E/SecOC tests (tests/test_protection.py) and the AV stream tests (tests/test_av.py), not only a successful build. Inspect results/canfd/report.json, results/mixed/verification.json, results/avtp/report.json, results/someip/report.json, results/protection/report.json and results/av/report.json.
- SecOC needs OpenSSL 3 development headers (libssl-dev). If doctor.sh reports them missing, do not install system packages yourself: report it, or with the user's consent run scripts/fetch-openssl-dev.sh (unpacks matching headers into .local/, no sudo).
- If prerequisites are missing, report the specific condition. Do not silently substitute framework versions or weaken tests.
- Report CLI/GUI launch commands and the limitations: selected CoRE application migration, unported AS6802/AVB parts, approximate CAN-FD timing, AVTP default configs use ideal time without TSN; AvtpTsn* configs use INET TSN (802.1Q, CBS, gPTP) with static SRP-equivalent forwarding (docs/AVTP.md); SOA4CoRE is ported for SOME/IP/SOME/IP-SD only (no AVB/SRP, QoS negotiation, gateways; docs/SOMEIP.md); E2E (P01/P02/P04/P05/P07) and SecOC protect CAN frames end to end and SOME/IP events, not SOME/IP-SD; single-window E2E state machine, static SecOC keys, zero MAC processing time, parts not yet checked against the AUTOSAR specification text (docs/PROTECTION.md); IEEE 1722 AV streams (AAF PCM, IEC 61883-4 MPEG-2 TS, CRF) carry synthetic data, no CVF/RVF/61883-6/AVDECC/SRP, timestamp semantics partly unverified against the standard text (docs/AV.md).
- Keep .local, upstream checkouts, credentials, build products, logs, and results out of commits. Publish source changes as patches plus tests/docs.
