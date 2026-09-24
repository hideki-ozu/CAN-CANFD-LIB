# Setup instructions for Claude Code

Read README.md before executing setup. It is the complete user-facing installation guide.

- Assume the user already installed and tested OMNeT++; preserve that installation.
- Resolve OMNETPP_ROOT from the user's supplied path or active OMNeT++ environment.
- Run scripts/doctor.sh, then BUILD_JOBS=4 scripts/setup.sh (reduce jobs for low memory).
- Normal setup must not call build-runtime.sh or setup-runtime-deps.sh. Do not change OMNeT++ configure.user, system packages, shell startup files, or authentication settings.
- Sources are pinned by sources.lock.json. Preserve local edits: no reset/clean to bypass commit or patch mismatches.
- Success requires native CAN/CAN-FD tests, all four mixed network configurations the IEEE 1722 AVTP tests (tests/test_avtp.py) and the SOME/IP tests (tests/test_someip.py), not only a successful build. Inspect results/canfd/report.json, results/mixed/verification.json, results/avtp/report.json and results/someip/report.json.
- If prerequisites are missing, report the specific condition. Do not silently substitute framework versions or weaken tests.
- Report CLI/GUI launch commands and the limitations: selected CoRE application migration, unported AS6802/AVB parts, approximate CAN-FD timing, AVTP default configs use ideal time without TSN; AvtpTsn* configs use INET TSN (802.1Q, CBS, gPTP) with static SRP-equivalent forwarding (docs/AVTP.md); SOA4CoRE is ported for SOME/IP/SOME/IP-SD only (no AVB/SRP, QoS negotiation, gateways; docs/SOMEIP.md).
- Keep .local, upstream checkouts, credentials, build products, logs, and results out of commits. Publish source changes as patches plus tests/docs.
