# Setup instructions for Claude Code

Read README.md before executing setup. It is the complete user-facing installation guide.

- Assume the user already installed and tested OMNeT++; preserve that installation.
- Resolve OMNETPP_ROOT from the user's supplied path or active OMNeT++ environment.
- Run scripts/doctor.sh, then BUILD_JOBS=4 scripts/setup.sh (reduce jobs for low memory).
- Normal setup must not call build-runtime.sh or setup-runtime-deps.sh. Do not change OMNeT++ configure.user, system packages, shell startup files, or authentication settings.
- Sources are pinned by sources.lock.json. Preserve local edits: no reset/clean to bypass commit or patch mismatches.
- Success requires native CAN/CAN-FD tests and all four mixed network configurations, not only a successful build. Inspect results/canfd/report.json and results/mixed/verification.json.
- If prerequisites are missing, report the specific condition. Do not silently substitute framework versions or weaken tests.
- Report CLI/GUI launch commands and the limitations: selected CoRE application migration, unported AS6802/AVB parts, approximate CAN-FD timing.
- Keep .local, upstream checkouts, credentials, build products, logs, and results out of commits. Publish source changes as patches plus tests/docs.
